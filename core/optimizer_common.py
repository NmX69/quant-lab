# core/optimizer_common.py
# Purpose: Shared helpers for optimizer modules (data loading, manifest loading, parameter grid building).
# Major External Functions/Classes:
#   - _load_and_prepare_df
#   - _build_param_combinations
#   - _load_manifest_pairs_for_timeframe
# Notes: Extracted from core/optimizer.py during Phase C refactor.

from __future__ import annotations

import json
import os
from itertools import product
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.config_manager import DATA_DIR, MANIFEST_FILE
from core.indicators import add_indicators_and_regime


def _load_and_prepare_df(asset_file: str, max_candles: int) -> pd.DataFrame:
    """
    Helper: load a CSV from DATA_DIR, parse timestamp, add indicators/regimes,
    and optionally truncate to last `max_candles` rows.
    """
    path = os.path.join(DATA_DIR, asset_file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found for optimization: {path}")

    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    df = add_indicators_and_regime(df)
    if df.empty:
        raise ValueError(f"No data after indicators in optimizer for file: {asset_file}")

    if max_candles and max_candles > 0:
        df = df.tail(max_candles).copy()
        df.reset_index(drop=True, inplace=True)

    return df


def _build_param_combinations(param_grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    Build list of dicts representing all combinations in param_grid.

    Example:
        param_grid = {
            "position_pct": [5.0, 10.0],
            "risk_pct": [0.5, 1.0],
        }

    Returns:
        [
            {"position_pct": 5.0, "risk_pct": 0.5},
            {"position_pct": 5.0, "risk_pct": 1.0},
            {"position_pct": 10.0, "risk_pct": 0.5},
            {"position_pct": 10.0, "risk_pct": 1.0},
        ]
    """
    if not param_grid:
        return []

    keys = list(param_grid.keys())
    values_lists = [param_grid[k] for k in keys]
    combos: List[Dict[str, Any]] = []

    for combo in product(*values_lists):
        d = {k: v for k, v in zip(keys, combo)}
        combos.append(d)

    return combos


def _load_manifest_pairs_for_timeframe(timeframe: str) -> List[Dict[str, str]]:
    """
    Load manifest.json and return a list of dicts:
        {"pair": ..., "timeframe": ..., "file": ..., "candles": ...}
    filtered by timeframe.
    """
    if not os.path.exists(MANIFEST_FILE):
        raise FileNotFoundError(f"Manifest file not found: {MANIFEST_FILE}")

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    pairs = manifest.get("pairs", {})
    results: List[Dict[str, str]] = []

    for pair, tf_data in pairs.items():
        for tf, meta in tf_data.items():
            if tf != timeframe:
                continue
            fname = meta.get("file")
            candles = meta.get("candles", "")
            if not fname:
                continue
            results.append(
                {
                    "pair": pair,
                    "timeframe": tf,
                    "file": fname,
                    "candles": candles,
                }
            )

    if not results:
        raise ValueError(f"No entries found in manifest for timeframe='{timeframe}'")

    return results

# core/optimizer_common.py v0.1 (115 lines)
