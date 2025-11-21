# core/fitness_cli.py
# Purpose: Simple CLI entrypoint for Phase D asset fitness runs.
# Major External Functions/Classes:
#   - main
# Notes: Thin wrapper around core.asset_fitness; safe to ignore in GUI contexts.

from __future__ import annotations

import argparse
from typing import List, Optional

from core.asset_fitness import (
    run_fitness_matrix,
    compute_stability_metrics,
    export_fitness_matrix,
)


def _parse_strategies(raw: str) -> List[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Quant-Lab Phase D – Asset Fitness CLI")
    parser.add_argument(
        "--strategies",
        type=str,
        required=True,
        help="Comma-separated list of strategy names (e.g. trend_macd,range_rsi_bb)",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default="1h",
        help="Comma-separated list of timeframes (default: 1h)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="balanced",
        help="Backtest mode (default: balanced)",
    )
    parser.add_argument(
        "--use-router",
        action="store_true",
        help="Use regime router instead of a single fixed strategy.",
    )
    parser.add_argument(
        "--max-candles",
        type=int,
        default=0,
        help="Max candles to use from each asset file (0 = all).",
    )
    parser.add_argument(
        "--position-pct",
        type=float,
        default=15.0,
        help="Position size as percent of equity (default: 15.0).",
    )
    parser.add_argument(
        "--risk-pct",
        type=float,
        default=1.0,
        help="Risk per trade as percent of equity (default: 1.0).",
    )
    parser.add_argument(
        "--reward-rr",
        type=float,
        default=None,
        help="Reward:risk multiple (default: None → mode default).",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Optional tag for output files (default: generated from mode/timeframes).",
    )

    args = parser.parse_args(argv)

    # Normalize to lists explicitly
    strategies = _parse_strategies(args.strategies)
    timeframes = _parse_strategies(args.timeframes)

    df = run_fitness_matrix(
        strategies=strategies,
        timeframes=timeframes,
        mode=args.mode,
        use_router=args.use_router,
        max_candles=args.max_candles,
        strategy_mappings=None,
        position_pct=args.position_pct,
        risk_pct=args.risk_pct,
        reward_rr=args.reward_rr,
        assets=None,
    )

    df = compute_stability_metrics(df)

    if args.tag:
        tag = args.tag
    else:
        tf_tag = "_".join(timeframes)
        tag = f"{args.mode}_{tf_tag}"

    csv_path, json_path = export_fitness_matrix(df, tag=tag)
    print(f"Saved fitness matrix to: {csv_path}")
    print(f"Saved fitness JSON to: {json_path}")


if __name__ == "__main__":
    main()

# core/fitness_cli.py v0.2 (114 lines)
