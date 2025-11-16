# core/strategy_loader.py
# PHASE 6: VALIDATION FOR NEW CONDITIONS (EMA/STOCH CROSS, ATR FIELDS)

import os
import json
from typing import Dict, List
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRATEGIES_DIR = os.path.join(PROJECT_ROOT, "strategies")

_STRATEGIES: Dict[str, Dict] = {}
_LOADED = False


def _validate_strategy(name: str, data: Dict) -> None:
    required = ["name", "regime", "direction", "entry", "exit", "risk"]
    for field in required:
        if field not in data:
            raise ValueError(f"Strategy '{name}': missing '{field}'")

    valid_regimes = ["trending", "trending_up", "trending_down", "ranging", "both"]
    if data["regime"] not in valid_regimes:
        raise ValueError(f"Strategy '{name}': invalid regime '{data['regime']}'. Must be one of {valid_regimes}")

    if data["direction"] not in ["long", "short", "both"]:
        raise ValueError(f"Strategy '{name}': invalid direction")

    if not isinstance(data["entry"].get("conditions"), list):
        raise ValueError(f"Strategy '{name}': entry.conditions must be list")

    if "stop_loss" not in data["exit"]:
        raise ValueError(f"Strategy '{name}': exit.stop_loss required")

    # Validate new risk fields
    sizing = data["risk"]["sizing"]
    if sizing == "atr" and "atr_multiplier" not in data["risk"]:
        raise ValueError(f"Strategy '{name}': atr sizing requires atr_multiplier")
    if sizing == "fixed_usd" and "max_exposure_usd" not in data["risk"]:
        raise ValueError(f"Strategy '{name}': fixed_usd requires max_exposure_usd")
    if sizing == "equity_pct" and "risk_per_trade_pct" not in data["risk"]:
        raise ValueError(f"Strategy '{name}': equity_pct requires risk_per_trade_pct")

    # Validate conditions
    valid_conditions = [
        "macd_cross", "ema_cross", "stochastic_cross", "adx", "rsi",
        "price_above_ema", "price_below_ema", "price_above_bb", "price_below_bb",
        "price_near_bb_lower", "price_crosses_mid_bb", "price_crosses_mid_bb_down",
        "volume_zscore"
    ]
    for cond in data["entry"]["conditions"]:
        if cond["type"] not in valid_conditions:
            raise ValueError(f"Strategy '{name}': invalid condition type '{cond['type']}'")
        if cond["type"] == "ema_cross":
            if "fast" not in cond or "slow" not in cond:
                raise ValueError(f"Strategy '{name}': ema_cross requires fast and slow periods")

    for cond in data["exit"].get("signal_exit", []):
        if cond["type"] not in valid_conditions:
            raise ValueError(f"Strategy '{name}': invalid exit condition type '{cond['type']}'")


def _create_fallback():
    fallback = {
        "name": "Fallback Trend",
        "regime": "trending",
        "direction": "long",
        "entry": {"conditions": [
            {"type": "macd_cross", "direction": "up"},
            {"type": "adx", "above": 25},
            {"type": "price_above_ema", "period": 150}
        ]},
        "exit": {
            "stop_loss": 0.03,
            "take_profit": 0.18,
            "partial_exit": 0.5,
            "signal_exit": [{"type": "macd_cross", "direction": "down"}]
        },
        "risk": {"sizing": "fixed_usd", "max_exposure_usd": 15.0}
    }
    _STRATEGIES["fallback_trend"] = fallback
    logger.info("Fallback strategy 'fallback_trend' loaded")


def load_strategies() -> None:
    """Load all *.json files from the strategies folder."""
    global _LOADED, _STRATEGIES
    if _LOADED:
        logger.info("Strategies already loaded.")
        return

    _STRATEGIES.clear()
    logger.info(f"Scanning strategies in: {STRATEGIES_DIR}")

    if not os.path.exists(STRATEGIES_DIR):
        logger.error(f"Strategies directory does not exist: {STRATEGIES_DIR}")
        _create_fallback()
        _LOADED = True
        return

    files = [f for f in os.listdir(STRATEGIES_DIR) if f.lower().endswith(".json")]
    logger.info(f"Found {len(files)} JSON files: {files}")

    if not files:
        logger.warning("No .json files found in strategies directory.")
        _create_fallback()
        _LOADED = True
        return

    loaded_any = False
    for filename in files:
        name = os.path.splitext(filename)[0].lower()
        path = os.path.join(STRATEGIES_DIR, filename)

        logger.info(f"Loading: {filename} → key: '{name}'")

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                logger.warning(f"File is empty: {filename}")
                continue

            data = json.loads(content)
            logger.info(f"JSON parsed: {data.get('name', 'Unnamed')}")

            _validate_strategy(name, data)
            _STRATEGIES[name] = data
            logger.info(f"Successfully loaded strategy: '{name}'")
            loaded_any = True

        except json.JSONDecodeError as e:
            logger.error(f"JSON ERROR in {filename}: {e} (line {e.lineno}, col {e.colno})")
        except Exception as e:
            logger.error(f"VALIDATION ERROR in {filename}: {e}")

    if not loaded_any:
        logger.warning("No valid strategies loaded — using fallback")
        _create_fallback()

    _LOADED = True
    logger.info(f"Strategy loading complete. Loaded keys: {list(_STRATEGIES.keys())}")


def get_strategy(name: str) -> Dict:
    """Return the loaded strategy dict for *name* (filename stem, lower‑cased)."""
    load_strategies()
    name = name.lower()
    if name not in _STRATEGIES:
        available = list(_STRATEGIES.keys())
        raise ValueError(f"Strategy '{name}' not found. Available: {available}")
    return _STRATEGIES[name]


def list_strategies() -> List[str]:
    """Return a sorted list of all loaded strategy keys."""
    load_strategies()
    return sorted(_STRATEGIES.keys())