# core/regime_router.py
# PHASE 2 — DUAL‑REGIME ROUTER — uses range_rsi_bb

from typing import Dict

from core.strategy_loader import get_strategy

DEFAULT_REGIME_TO_STRATEGY = {
    "trending_up": "trend_macd",
    "trending_down": "trend_macd",
    "ranging": "range_rsi_bb",          # ← now correct
}


def get_active_strategy(regime: str, mappings: Dict[str, str] = None) -> Dict:
    if mappings is None:
        mappings = DEFAULT_REGIME_TO_STRATEGY
    strategy_name = mappings.get(regime)
    if not strategy_name:
        raise ValueError(f"No strategy mapped for regime: {regime}")
    return get_strategy(strategy_name)