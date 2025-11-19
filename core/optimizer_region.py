# core/optimizer_region.py
# Purpose: Shared region filtering & summarization for optimizer results (C4).
# Major External Functions/Classes:
#   - select_good_region
#   - summarize_region
# Notes: Used by optimizer GUIs to focus on "good" parameter regions.

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def select_good_region(
    df: pd.DataFrame,
    *,
    min_sharpe: Optional[float] = None,
    max_dd_pct: Optional[float] = None,
    min_trades: Optional[int] = None,
    min_return_pct: Optional[float] = None,
) -> pd.DataFrame:
    """
    Filter an optimizer result DataFrame down to a "good region" based on simple constraints.

    Columns expected (not all must be present):
        - sharpe
        - max_dd_pct
        - total_trades
        - total_return_pct
        - grid_search_strategy_params_single_asset

    All constraints are optional; any that refer to missing columns are quietly ignored.

    Args:
        df: Optimizer result DataFrame.
        min_sharpe: Keep rows with sharpe >= this value.
        max_dd_pct: Keep rows with max_dd_pct <= this value.
        min_trades: Keep rows with total_trades >= this value.
        min_return_pct: Keep rows with total_return_pct >= this value.

    Returns:
        Filtered DataFrame (possibly empty), *not* sorted.
    """
    if df is None or df.empty:
        return df

    df_f = df.copy()

    if min_sharpe is not None and "sharpe" in df_f.columns:
        df_f = df_f[df_f["sharpe"] >= min_sharpe]

    if max_dd_pct is not None and "max_dd_pct" in df_f.columns:
        df_f = df_f[df_f["max_dd_pct"] <= max_dd_pct]

    if min_trades is not None and "total_trades" in df_f.columns:
        df_f = df_f[df_f["total_trades"] >= min_trades]

    if min_return_pct is not None and "total_return_pct" in df_f.columns:
        df_f = df_f[df_f["total_return_pct"] >= min_return_pct]

    # Reset index after filtering
    df_f = df_f.reset_index(drop=True)
    return df_f


def summarize_region(
    df: pd.DataFrame,
    *,
    min_sharpe: Optional[float] = None,
    max_dd_pct: Optional[float] = None,
    min_trades: Optional[int] = None,
    min_return_pct: Optional[float] = None,
    top_n: int = 20,
    sort_by: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Apply region filters (same as select_good_region) and then return the *top N* rows.

    Args:
        df: Full optimizer result DataFrame.
        min_sharpe, max_dd_pct, min_trades, min_return_pct: Region constraints.
        top_n: Number of rows to keep after sorting.
        sort_by: Explicit sort columns; if None, defaults to ["total_return_pct", "sharpe"].

    Returns:
        A new DataFrame with at most `top_n` rows.
    """
    if df is None or df.empty:
        return df

    df_f = select_good_region(
        df,
        min_sharpe=min_sharpe,
        max_dd_pct=max_dd_pct,
        min_trades=min_trades,
        min_return_pct=min_return_pct,
    )

    if df_f.empty:
        # If filters nuked everything, fallback to full df
        df_f = df.copy()

    if sort_by is None:
        sort_cols = []
        sort_order = []

        if "total_return_pct" in df_f.columns:
            sort_cols.append("total_return_pct")
            sort_order.append(False)
        if "sharpe" in df_f.columns:
            sort_cols.append("sharpe")
            sort_order.append(False)

        if not sort_cols:
            sort_cols = df_f.columns.tolist()
            sort_order = [False] * len(sort_cols)
    else:
        sort_cols = sort_by
        sort_order = [False] * len(sort_cols)

    if not sort_cols:
        return df_f.head(top_n).copy()

    df_sorted = df_f.sort_values(
        by=sort_cols,
        ascending=sort_order,
        ignore_index=True,
    )
    return df_sorted.head(top_n).copy()

# core/optimizer_region.py v0.1 (132 lines)
