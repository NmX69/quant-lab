# core/optimizer_engine.py
# Purpose: Engine-level grid search over risk/position envelopes (C1/C2).
# Major External Functions/Classes:
#   - grid_search_single_asset
#   - grid_search_all_assets
# Notes: Uses core.optimizer_common helpers and core.engine.run_backtest.

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from core.engine import run_backtest
from core.optimizer_common import (
    _load_and_prepare_df,
    _build_param_combinations,
    _load_manifest_pairs_for_timeframe,
)


def grid_search_single_asset(
    asset_file: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
    param_grid: Dict[str, List[float]],
    max_candles: int = 0,
    strategy_mappings: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Run a grid search over engine-level risk/position parameters for a single asset/strategy.

    This function:
        - Loads the CSV from DATA_DIR.
        - Applies indicators/regime classification once.
        - For each parameter combination, calls engine.run_backtest() with:
            * position_pct
            * risk_pct
            * reward_rr
        - Collects core metrics from BacktestResult.

    Returns:
        pd.DataFrame with one row per parameter combo, including:
            - position_pct
            - risk_pct
            - reward_rr
            - final_equity
            - total_return_pct
            - sharpe
            - max_dd_pct
            - total_trades
            - winrate

        Sorted by total_return_pct (descending), then Sharpe.
    """
    df = _load_and_prepare_df(asset_file, max_candles)
    combos = _build_param_combinations(param_grid)

    rows: List[Dict[str, float]] = []

    for params in combos:
        pos_pct = params["position_pct"]
        risk_pct = params["risk_pct"]
        rr = params["reward_rr"]

        try:
            summary, result = run_backtest(
                df=df,
                mode=mode,
                strategy_name=strategy_name,
                use_router=use_router,
                strategy_mappings=strategy_mappings,
                position_pct=pos_pct,
                risk_pct=risk_pct,
                reward_rr=rr,
            )

            if result is None:
                # Defensive check; current engine should not return None for non-empty df.
                continue

            rows.append(
                {
                    "position_pct": pos_pct,
                    "risk_pct": risk_pct,
                    "reward_rr": rr,
                    "final_equity": float(result.final_equity),
                    "total_return_pct": float(result.total_return_pct),
                    "sharpe": float(result.sharpe),
                    "max_dd_pct": float(result.max_dd_pct),
                    "total_trades": int(result.total_trades),
                    "winrate": float(result.winrate),
                }
            )
        except Exception:
            # In pathological cases, still record that this combo failed so the surface is complete.
            rows.append(
                {
                    "position_pct": pos_pct,
                    "risk_pct": risk_pct,
                    "reward_rr": rr,
                    "final_equity": float("nan"),
                    "total_return_pct": float("nan"),
                    "sharpe": float("nan"),
                    "max_dd_pct": float("nan"),
                    "total_trades": 0,
                    "winrate": 0.0,
                }
            )

    if not rows:
        return pd.DataFrame()

    df_res = pd.DataFrame(rows)
    df_res = df_res.sort_values(
        by=["total_return_pct", "sharpe"],
        ascending=[False, False],
        ignore_index=True,
    )
    return df_res


def grid_search_all_assets(
    timeframe: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
    param_grid: Dict[str, List[float]],
    max_candles: int = 0,
    strategy_mappings: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    For a given timeframe and strategy, run a parameter grid search for each asset
    listed in manifest.json, and return a summary of the *best* combo per asset.

    Each asset:
        - Runs grid_search_single_asset(...)
        - Takes the best row (highest total_return_pct, then Sharpe)
        - Annotates with asset/timeframe

    Returns:
        pd.DataFrame with columns:
            - asset
            - timeframe
            - position_pct
            - risk_pct
            - reward_rr
            - final_equity
            - total_return_pct
            - sharpe
            - max_dd_pct
            - total_trades
            - winrate
        Sorted by total_return_pct descending, then Sharpe.
    """
    entries = _load_manifest_pairs_for_timeframe(timeframe)
    rows: List[Dict[str, float]] = []

    for entry in entries:
        asset_file = entry["file"]
        pair = entry["pair"]
        tf = entry["timeframe"]

        df_asset = grid_search_single_asset(
            asset_file=asset_file,
            strategy_name=strategy_name,
            mode=mode,
            use_router=use_router,
            param_grid=param_grid,
            max_candles=max_candles,
            strategy_mappings=strategy_mappings,
        )

        if df_asset.empty:
            continue

        # Take the best row for this asset
        best = df_asset.iloc[0].to_dict()
        best_row = {
            "asset": pair,
            "timeframe": tf,
            **best,
        }
        rows.append(best_row)

    if not rows:
        return pd.DataFrame()

    df_res = pd.DataFrame(rows)
    df_res = df_res.sort_values(
        by=["total_return_pct", "sharpe"],
        ascending=[False, False],
        ignore_index=True,
    )
    return df_res

# core/optimizer_engine.py v0.1 (198 lines)
