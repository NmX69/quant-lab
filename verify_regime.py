#!/usr/bin/env python
"""
Simple regime verification tool.

- Loads a normalized OHLCV CSV from ./data
- Applies core.indicators.add_indicators_and_regime
- Prints counts of each regime and number of regime changes
"""

import argparse
import os
import sys

import pandas as pd

from core.indicators import add_indicators_and_regime


def detect_regime(row: pd.Series) -> str:
    """Return 'up', 'down', or 'ranging' based on regime flags on a single row."""
    if bool(row.get("trending_up", False)):
        return "up"
    if bool(row.get("trending_down", False)):
        return "down"
    return "ranging"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify regime classification on a symbol/interval CSV."
    )
    parser.add_argument(
        "--csv",
        default="data/ADAUSDT_1h.csv",
        help="Path to CSV file (default: data/ADAUSDT_1h.csv)",
    )
    parser.add_argument(
        "--max-candles",
        type=int,
        default=5000,
        help="Use only the last N candles (default: 5000)",
    )
    args = parser.parse_args()

    csv_path = args.csv

    if not os.path.exists(csv_path):
        print(f"[ERROR] CSV not found: {csv_path}")
        return 1

    print(f"Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])

    total_raw = len(df)
    if total_raw == 0:
        print("[ERROR] CSV is empty.")
        return 1

    if args.max_candles > 0 and total_raw > args.max_candles:
        df = df.iloc[-args.max_candles :].copy()
        print(f"Using last {len(df)} candles (from {total_raw} total)")
    else:
        df = df.copy()
        print(f"Using all {len(df)} candles")

    # Add indicators + regime columns
    df = add_indicators_and_regime(df)

    if df.empty:
        print("[ERROR] No rows left after indicator/regime calculation.")
        return 1

    # Regime counts
    up = int(df["trending_up"].sum())
    down = int(df["trending_down"].sum())
    ranging = int(df["ranging"].sum())
    total = len(df)

    # Compute a simple regime label per row
    regimes = df.apply(detect_regime, axis=1)
    # Count changes where regime != previous regime
    changes = int((regimes != regimes.shift(1)).sum())

    start_ts = df["timestamp"].iloc[0]
    end_ts = df["timestamp"].iloc[-1]

    print(
        f"""
REGIME VERIFICATION
===================
File:        {csv_path}
Rows used:   {total} (after indicators)
Date range:  {start_ts} -> {end_ts}

TRENDING_UP:   {up}
TRENDING_DOWN: {down}
RANGING:       {ranging}
REGIME CHANGES:{changes}
"""
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
