# core/backtest_runner.py
# Purpose: Run single, all-strategy, and all-asset backtests without any GUI dependencies.
# Major External Functions/Classes: run_single_backtest, run_all_strategies_backtest, run_all_assets_backtest
# Notes: Uses core.engine.run_backtest and core.indicators.add_indicators_and_regime.

import json
import os
import re
from decimal import Decimal
from typing import Dict, Optional, Tuple

import pandas as pd

from core.engine import run_backtest
from core.indicators import add_indicators_and_regime
from core.strategy_loader import list_strategies
from core.results import BacktestResult
from core.config_manager import DATA_DIR, RESULTS_DIR, MANIFEST_FILE


def _make_header(asset: str, strat: str, use_router: bool) -> str:
    asset_sym = asset.split("_")[0]
    if use_router:
        return f"BACKTEST (router) – {asset_sym}"
    return f"BACKTEST: {strat} – {asset_sym}"


def run_single_backtest(
    asset_file: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
    max_candles: int,
    strategy_mappings: Optional[Dict],
    position_pct: float,
    risk_pct: float,
    reward_rr: float,
) -> Tuple[str, str, BacktestResult]:
    """
    Run a single backtest for one asset/strategy combination.

    Returns:
        preamble_text: info about loaded rows, indicators, and header.
        summary_text: formatted summary from BacktestResult.summary_str() with header fixed.
        result: BacktestResult with trades saved to RESULTS_DIR.
    """
    path = os.path.join(DATA_DIR, asset_file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")

    # Load CSV
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    preamble_lines = [
        f"Loaded {len(df):,} rows from {os.path.basename(path)}",
        "",
    ]

    # Indicators + regime
    df = add_indicators_and_regime(df)
    if df.empty:
        raise ValueError("No data after indicators")

    preamble_lines.append(f"Indicators ready: {len(df):,} valid rows")
    preamble_lines.append("")

    # Limit candles if requested
    if max_candles and max_candles < len(df):
        df = df.tail(max_candles)

    header = _make_header(asset_file, strategy_name, use_router)
    preamble_lines.append("Starting backtest…")
    preamble_lines.append(header)
    preamble_lines.append(f"Mode: {mode}")
    preamble_lines.append(f"Using last {len(df)} candles")
    preamble_lines.append("")

    # Run engine-level backtest
    summary, result = run_backtest(
        df,
        mode,
        strategy_name,
        use_router=use_router,
        strategy_mappings=strategy_mappings,
        position_pct=position_pct,
        risk_pct=risk_pct,
        reward_rr=reward_rr,
    )

    result.asset = asset_file.split("_")[0]
    result.save_trades(RESULTS_DIR)

    # Fix header line to be consistent with GUI's expectations
    lines = summary.splitlines()
    if len(lines) > 1:
        lines[1] = header
    summary_fixed = "\n".join(lines)

    preamble_text = "\n".join(preamble_lines) + "\n"
    return preamble_text, summary_fixed, result


def run_all_strategies_backtest(
    asset_file: str,
    mode: str,
    max_candles: int,
    position_pct: float,
    risk_pct: float,
    reward_rr: float,
) -> Tuple[pd.DataFrame, str]:
    """
    Run backtests for all strategies on a single asset.

    Returns:
        df_res: DataFrame with columns [Strategy, Final, Return %, Trades, Max DD %].
        error_log: string with per-strategy error lines (possibly empty).
    """
    path = os.path.join(DATA_DIR, asset_file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = add_indicators_and_regime(df)
    if max_candles and max_candles < len(df):
        df = df.tail(max_candles)

    results = []
    error_lines = []

    for s in list_strategies():
        try:
            summ, _ = run_backtest(
                df,
                mode,
                s,
                use_router=False,
                strategy_mappings=None,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
            final = float(re.search(r"Final: \$([\d,]+\.\d+)", summ).group(1).replace(",", ""))
            ret = float(re.search(r"Return: ([\-\+\d\.]+)%", summ).group(1))
            trd = int(re.search(r"Trades: (\d+)", summ).group(1))
            ddpc = float(re.search(r"\((\d+\.\d+)%\)", summ).group(1))
            results.append(
                {
                    "Strategy": s,
                    "Final": final,
                    "Return %": ret,
                    "Trades": trd,
                    "Max DD %": ddpc,
                }
            )
        except Exception as e:
            error_lines.append(f"Error on {s}: {str(e)}")

    df_res = pd.DataFrame(results) if results else pd.DataFrame()
    error_log = ("\n".join(error_lines) + "\n") if error_lines else ""
    return df_res, error_log


def run_all_assets_backtest(
    timeframe: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
    max_candles: int,
    strategy_mappings: Optional[Dict],
    position_pct: float,
    risk_pct: float,
    reward_rr: float,
) -> Tuple[pd.DataFrame, str]:
    """
    Run backtests for a single strategy across all assets in manifest.json for a given timeframe.

    Returns:
        df_res: DataFrame with columns [Asset, Final, Return %, Trades, Max DD %].
        error_log: string with per-asset error lines (possibly empty).
    """
    if not os.path.exists(MANIFEST_FILE):
        raise FileNotFoundError("manifest.json not found")

    with open(MANIFEST_FILE, "r") as f:
        manifest = json.load(f)

    results = []
    error_lines = []

    for pair, data in manifest["pairs"].items():
        if timeframe not in data:
            continue
        file = data[timeframe]["file"]
        path = os.path.join(DATA_DIR, file)
        try:
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = add_indicators_and_regime(df)
            if max_candles and max_candles < len(df):
                df = df.tail(max_candles)

            summ, result = run_backtest(
                df,
                mode,
                strategy_name,
                use_router=use_router,
                strategy_mappings=strategy_mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
            result.asset = pair
            result.save_trades(RESULTS_DIR)

            final = float(re.search(r"Final: \$([\d,]+\.\d+)", summ).group(1).replace(",", ""))
            ret = float(re.search(r"Return: ([\-\+\d\.]+)%", summ).group(1))
            trd = int(re.search(r"Trades: (\d+)", summ).group(1))
            ddpc = float(re.search(r"\((\d+\.\d+)%\)", summ).group(1))
            results.append(
                {
                    "Asset": pair,
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

# core/backtest_runner.py v1.0 (237 lines)
