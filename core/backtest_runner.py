# core/backtest_runner.py
# Purpose: Run single, all-strategy, and all-asset backtests without any GUI dependencies.
# Major APIs: run_single_backtest, run_all_strategies_backtest, run_all_assets_backtest
# Notes: Uses core.engine.run_backtest, core.indicators.add_indicators_and_regime, and core.reporting.

import json
import os
import re
from typing import Dict, Optional, Tuple, List

import pandas as pd

from core.engine import run_backtest
from core.indicators import add_indicators_and_regime
from core.strategy_loader import list_strategies
from core.results import BacktestResult
from core.reporting import build_report, export_report_json, export_report_csv
from core.config_manager import DATA_DIR, RESULTS_DIR, MANIFEST_FILE


def _load_dataframe(asset_file: str, max_candles: int) -> Tuple[pd.DataFrame, str]:
    """
    Load a CSV from data/ and optionally truncate to the last `max_candles` rows.
    Returns (df, preamble_header_str).
    """
    path = os.path.join(DATA_DIR, asset_file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_csv(path)
    total = len(df)

    if max_candles and max_candles > 0 and total > max_candles:
        df = df.tail(max_candles)

    used = len(df)
    preamble_lines = [
        f"Running backtest for {asset_file} | Max candles: {max_candles or 'ALL'}",
        f"Available: {total} candles",
        f"Using {used} of {total} available candles.",
        "",
    ]
    preamble = "\n".join(preamble_lines) + "\n"
    return df, preamble


def _apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply indicators and regime detection to the DataFrame.
    """
    df_ind = add_indicators_and_regime(df)
    if df_ind is None or df_ind.empty:
        raise ValueError("No data after indicators")
    return df_ind


def _sanitize_name(name: str) -> str:
    """
    Sanitize file-friendly name (for reports/trades filenames).
    """
    return re.sub(r"[^A-Za-z0-9_]+", "_", name)


def _save_trades_and_report(
    result: BacktestResult,
    asset_file: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
) -> None:
    """
    Save trades CSV (via BacktestResult.save_trades) and Phase B analytics report
    (JSON + CSV) into RESULTS_DIR.

    The report filenames are of the form:
      report_<asset>_<strategy>_<mode>[ _router].json
      report_<asset>_<strategy>_<mode>[ _router].csv
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Phase A artifact: trades CSV
    result.save_trades(RESULTS_DIR)

    # Phase B artifact: analytics report
    report = build_report(result)

    base_asset = os.path.splitext(os.path.basename(asset_file))[0]
    base_asset = _sanitize_name(base_asset)
    strat = _sanitize_name(strategy_name)
    mode_s = _sanitize_name(mode)
    router_suffix = "_router" if use_router else ""

    json_path = os.path.join(
        RESULTS_DIR, f"report_{base_asset}_{strat}_{mode_s}{router_suffix}.json"
    )
    csv_path = os.path.join(
        RESULTS_DIR, f"report_{base_asset}_{strat}_{mode_s}{router_suffix}.csv"
    )

    export_report_json(report, json_path)
    export_report_csv(report, csv_path)


def run_single_backtest(
    asset_file: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
    max_candles: int,
    strategy_mappings: Optional[Dict[str, str]],
    position_pct: float,
    risk_pct: float,
    reward_rr: float,
) -> Tuple[str, str, BacktestResult]:
    """
    Run one backtest (one asset, one strategy or router) and return:
      - preamble_text
      - summary_text
      - BacktestResult

    Phase B: also writes a report JSON/CSV in RESULTS_DIR as a side effect.
    """
    df, preamble = _load_dataframe(asset_file, max_candles)
    df = _apply_indicators(df)

    summary_text, result = run_backtest(
        df=df,
        mode=mode,
        strategy_name=strategy_name,
        use_router=use_router,
        strategy_mappings=strategy_mappings,
        position_pct=position_pct,
        risk_pct=risk_pct,
        reward_rr=reward_rr,
    )

    if not isinstance(result, BacktestResult):
        raise ValueError("run_backtest did not return a BacktestResult")

    # Tag the result with the correct asset + mode
    base_asset = os.path.splitext(os.path.basename(asset_file))[0]
    result.asset = base_asset
    result.mode = mode

    # Cosmetic header fix: replace 'unknown' with the asset name for router runs
    summary_text = summary_text.replace(
        "BACKTEST (router) – unknown", f"BACKTEST (router) – {base_asset}"
    )

    # Phase B integration: save trades + analytics report
    _save_trades_and_report(
        result=result,
        asset_file=asset_file,
        strategy_name=strategy_name,
        mode=mode,
        use_router=use_router,
    )

    # Ensure summary text has a standard header
    header = (
        "\n============================================================\n"
        "REGIME-AWARE BACKTEST SUMMARY\n"
        "============================================================\n"
    )
    if not summary_text.startswith("\n==="):
        summary_text = header + summary_text

    return preamble, summary_text, result


def run_all_strategies_backtest(
    asset_file: str,
    mode: str,
    max_candles: int,
    position_pct: float,
    risk_pct: float,
    reward_rr: float,
) -> Tuple[pd.DataFrame, str]:
    """
    Run all strategies on a single asset and return:
      - DataFrame with Strategy / Final / Return % / Trades / Max DD %
      - error_log string

    Phase B: does NOT currently generate per-strategy reports to avoid excess files.
    """
    df, _ = _load_dataframe(asset_file, max_candles)
    df = _apply_indicators(df)

    results: List[Dict[str, object]] = []
    error_lines: List[str] = []

    for strat in list_strategies():
        try:
            _, result = run_backtest(
                df=df,
                mode=mode,
                strategy_name=strat,
                use_router=False,
                strategy_mappings=None,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
            if not isinstance(result, BacktestResult):
                raise ValueError("run_backtest did not return BacktestResult")

            final = float(result.final_equity)
            ret = float(result.total_return_pct)
            trd = int(result.total_trades)
            ddpc = float(result.max_dd_pct)

            results.append(
                {
                    "Strategy": strat,
                    "Final": final,
                    "Return %": ret,
                    "Trades": trd,
                    "Max DD %": ddpc,
                }
            )
        except Exception as e:
            error_lines.append(f"Error on strategy {strat}: {str(e)}")

    df_res = pd.DataFrame(results) if results else pd.DataFrame()
    error_log = ("\n".join(error_lines) + "\n") if error_lines else ""
    return df_res, error_log


def run_all_assets_backtest(
    timeframe: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
    max_candles: int,
    strategy_mappings: Optional[Dict[str, str]],
    position_pct: float,
    risk_pct: float,
    reward_rr: float,
) -> Tuple[pd.DataFrame, str]:
    """
    Run a single strategy (or router) across all assets in manifest.json
    for a given timeframe.

    Returns:
      - DataFrame with Asset / Final / Return % / Trades / Max DD %
      - error_log string
    """
    if not os.path.exists(MANIFEST_FILE):
        raise FileNotFoundError(f"Manifest file not found: {MANIFEST_FILE}")

    with open(MANIFEST_FILE, "r") as f:
        manifest = json.load(f)

    pairs = manifest.get("pairs", {})
    results: List[Dict[str, object]] = []
    error_lines: List[str] = []

    for pair, tf_data in pairs.items():
        if timeframe not in tf_data:
            continue

        asset_file = tf_data[timeframe]["file"]
        candles_available = tf_data[timeframe].get("candles")

        try:
            df, _ = _load_dataframe(asset_file, max_candles)
            df = _apply_indicators(df)

            _, result = run_backtest(
                df=df,
                mode=mode,
                strategy_name=strategy_name,
                use_router=use_router,
                strategy_mappings=strategy_mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
            if not isinstance(result, BacktestResult):
                raise ValueError("run_backtest did not return BacktestResult")

            final = float(result.final_equity)
            ret = float(result.total_return_pct)
            trd = int(result.total_trades)
            ddpc = float(result.max_dd_pct)

            results.append(
                {
                    "Asset": pair,
                    "Candles": candles_available if candles_available is not None else "",
                    "Final": final,
                    "Return %": ret,
                    "Trades": trd,
                    "Max DD %": ddpc,
                }
            )
        except Exception as e:
            error_lines.append(f"Error on {pair}: {str(e)}")

    df_res = pd.DataFrame(results) if results else pd.DataFrame()
    error_log = ("\n".join(error_lines) + "\n") if error_lines else ""
    return df_res, error_log

# core/backtest_runner.py v1.3 (304 lines)
