# core/strategy_loader.py
# Purpose: Load SDL JSON strategies from disk, resolve inheritance, validate them, and expose lookup helpers.
# API's: load_strategies, get_strategy, list_strategies
# Notes: Uses sdl_validator for schema enforcement and supports optional 'extends' inheritance.

import copy
import json
import logging
import os
from typing import Dict, List

from core.sdl_validator import ValidationError, validate_strategy_dict

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRATEGIES_DIR = os.path.join(PROJECT_ROOT, "strategies")

_STRATEGIES: Dict[str, Dict] = {}
_LOADED: bool = False


def _validate_strategy(name: str, data: Dict) -> None:
    """Validate a single strategy using the SDL validator.

    Raises:
        ValueError: if any validation errors are present.
    """

    errors = validate_strategy_dict(name, data)
    if errors:
        joined = "; ".join(f"{err.path}: {err.message}" for err in errors)
        raise ValueError(joined)


def _create_fallback() -> None:
    """Install a hard-coded fallback strategy when no JSON files can be loaded."""

    fallback = {
        "name": "Fallback Trend",
        "regime": "trending",
        "direction": "long",
        "entry": {
            "conditions": [
                {"type": "macd_cross", "direction": "up"},
                {"type": "adx", "above": 25},
                {"type": "price_above_ema", "period": 150},
            ]
        },
        "exit": {
            "stop_loss": 0.03,
            "take_profit": 0.18,
            "partial_exit": 0.5,
            "signal_exit": [{"type": "macd_cross", "direction": "down"}],
        },
        "risk": {"sizing": "fixed_usd", "max_exposure_usd": 15.0},
    }
    _STRATEGIES["fallback_trend"] = fallback
    logger.info("Fallback strategy 'fallback_trend' loaded")


def _resolve_inheritance(raw_strategies: Dict[str, Dict]) -> Dict[str, Dict]:
    """Resolve optional 'extends' inheritance between strategies.

    Each strategy may define::

        "extends": "base_strategy_key"

    The resolution rules are:

    * If no 'extends' is present, the strategy is used as-is (deep-copied).
    * If 'extends' is present, the base strategy is resolved first, then the
      child is shallow-merged on top at the top level. Complex sections like
      'entry', 'exit', and 'risk' are replaced as whole blocks by the child
      when provided.
    * Inheritance cycles raise ValueError with a descriptive message.
    * Referencing a non-existent base strategy also raises ValueError.
    """

    resolved: Dict[str, Dict] = {}
    visiting: set[str] = set()

    def resolve(name: str) -> Dict:
        if name in resolved:
            return resolved[name]
        if name not in raw_strategies:
            raise ValueError(
                f"Strategy '{name}' referenced in 'extends' but no JSON file found"
            )
        if name in visiting:
            cycle = " -> ".join(list(visiting) + [name])
            raise ValueError(f"Inheritance cycle detected: {cycle}")

        visiting.add(name)
        data = raw_strategies[name]

        base_key = data.get("extends")
        if base_key:
            base_key_lower = str(base_key).lower()
            base_resolved = resolve(base_key_lower)
            base_copy = copy.deepcopy(base_resolved)
            child_copy = copy.deepcopy(data)
            # Do not keep 'extends' in the final resolved strategy.
            child_copy.pop("extends", None)
            # Shallow top-level merge: child keys override base keys entirely.
            base_copy.update(child_copy)
            merged = base_copy
        else:
            merged = copy.deepcopy(data)

        resolved[name] = merged
        visiting.remove(name)
        return merged

    for key in raw_strategies.keys():
        resolve(key)

    return resolved


def load_strategies() -> None:
    """Load all *.json files from the strategies folder.

    This function is idempotent: repeated calls will return immediately once
    the strategies are loaded.
    """

    global _LOADED, _STRATEGIES
    if _LOADED:
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

    raw_strategies: Dict[str, Dict] = {}
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

            raw_strategies[name] = data
            loaded_any = True

        except json.JSONDecodeError as e:
            logger.error(
                f"JSON ERROR in {filename}: {e} (line {e.lineno}, col {e.colno})"
            )
        except Exception as e:
            logger.error(f"ERROR while loading {filename}: {e}")

    if not loaded_any:
        logger.warning("No valid strategies loaded — using fallback")
        _STRATEGIES.clear()
        _create_fallback()
        _LOADED = True
        logger.info(
            f"Strategy loading complete. Loaded keys: {list(_STRATEGIES.keys())}",
        )
        return

    # Resolve inheritance (extends) and validate resolved strategies.
    try:
        resolved = _resolve_inheritance(raw_strategies)
    except Exception as e:
        logger.error(f"Error while resolving strategy inheritance: {e}")
        _STRATEGIES.clear()
        _create_fallback()
        _LOADED = True
        logger.info(
            f"Strategy loading complete. Loaded keys: {list(_STRATEGIES.keys())}",
        )
        return

    validated: Dict[str, Dict] = {}
    for name, data in resolved.items():
        try:
            _validate_strategy(name, data)
            validated[name] = data
            logger.info(f"Successfully loaded strategy: '{name}'")
        except Exception as e:
            logger.error(f"VALIDATION ERROR in '{name}': {e}")

    if not validated:
        logger.warning("No valid strategies after validation — using fallback")
        _STRATEGIES.clear()
        _create_fallback()
    else:
        _STRATEGIES = validated

    _LOADED = True
    logger.info(
        f"Strategy loading complete. Loaded keys: {list(_STRATEGIES.keys())}",
    )


def get_strategy(name: str) -> Dict:
    """Return the loaded strategy dict for *name* (filename stem, lower-cased)."""

    load_strategies()
    key = name.lower()
    if key not in _STRATEGIES:
        available = list(_STRATEGIES.keys())
        raise ValueError(
            f"Strategy '{key}' not found. Available: {available}",
        )
    return _STRATEGIES[key]


def list_strategies() -> List[str]:
    """Return a sorted list of all loaded strategy keys."""

    load_strategies()
    return sorted(_STRATEGIES.keys())
# core/strategy_loader.py v1.3 (244 lines)
