# core/sdl_schema.py
# Purpose: Define SDL schema metadata (required fields, enums, and section-level requirements) for strategy JSON files.
# API's: STRATEGY_REQUIRED_FIELDS, VALID_REGIMES, VALID_DIRECTIONS, VALID_SIZING, VALID_CONDITION_TYPES, VALID_TIMEFRAMES, VALID_MTF_ROLES
# Notes: Pure metadata; consumed by sdl_validator and strategy_loader.

from typing import List

# Top-level required fields for a fully-specified strategy. Children that use
# 'extends' may omit some of these and inherit them from a base strategy.
STRATEGY_REQUIRED_FIELDS: List[str] = [
    "name",
    "regime",
    "direction",
    "entry",
    "exit",
    "risk",
]

# Allowed regime strings for the current SDL version.
VALID_REGIMES: List[str] = [
    "trending",
    "trending_up",
    "trending_down",
    "ranging",
    "both",
]

# Allowed trade directions.
VALID_DIRECTIONS: List[str] = [
    "long",
    "short",
    "both",
]

# Allowed risk sizing modes.
VALID_SIZING: List[str] = [
    "equity_pct",
    "atr",
    "fixed_usd",
]

# Allowed condition types for entry/exit/MTF signal evaluation.
VALID_CONDITION_TYPES: List[str] = [
    "macd_cross",
    "ema_cross",
    "stochastic_cross",
    "adx",
    "rsi",
    "price_above_ema",
    "price_below_ema",
    "price_above_bb",
    "price_below_bb",
    "price_near_bb_lower",
    "price_near_bb_upper",
    "price_crosses_mid_bb",
    "price_crosses_mid_bb_down",
    "volume_zscore",
    # Phase F4 additions: higher-level primitives built on existing indicators.
    "breakout_high",
    "breakout_low",
    "volatility_expansion",
    "range_contraction",
    "trend_pullback",
]

# Allowed timeframes for multi-timeframe (MTF) sections. These are advisory for
# Phase F and will be enforced in Phase I when MTF execution is implemented.
VALID_TIMEFRAMES: List[str] = [
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "12h",
    "1d",
    "3d",
    "1w",
]

# Allowed semantic roles for MTF blocks. These are descriptive only for now and
# do not affect execution until Phase I wires them into the engine.
VALID_MTF_ROLES: List[str] = [
    "trend_filter",
    "confirmation",
    "regime_filter",
    "volatility_filter",
]
# core/sdl_schema.py v0.4 (92 lines)
