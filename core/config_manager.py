# core/config_manager.py
# Purpose: Centralize project paths and Quant-Lab configuration load/save.
# Major External Functions/Classes: load_config, save_config
# Notes: PROJECT_ROOT is the repo root (parent of core/).

import json
import os
from typing import Dict, Any


# Compute project root as parent of this core/ directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MANIFEST_FILE = os.path.join(DATA_DIR, "manifest.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")


_DEFAULT_CONFIG: Dict[str, Any] = {
    "data_file": "",
    "timeframe": "1h",
    "strategy": "",
    "mode": "balanced",
    "candles": 0,
    "show_equity": True,
    "run_mode": "Single",
    "use_router": False,
    "trending_up_strategy": "trend_macd",
    "trending_down_strategy": "trend_macd",
    "ranging_strategy": "range_rsi_bb",
    # Risk / sizing defaults (GUI sliders)
    "position_pct": 15.0,   # % of equity used as notional per trade
    "risk_pct": 1.0,        # % of equity risked per trade
    "reward_rr": 1.5,       # reward:risk multiple
}


def load_config() -> Dict[str, Any]:
    """
    Load Quant-Lab configuration from disk, merged with defaults.

    Returns:
        dict with all expected keys present.
    """
    cfg = _DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
            cfg.update(loaded)
        except Exception:
            # If config is corrupt, silently fall back to defaults.
            pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    """
    Persist configuration dict to CONFIG_FILE.

    Args:
        cfg: dict of primitive values (JSON-serializable).
    """
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        # Config persistence failure should not crash the GUI.
        pass

# core/config_manager.py v1.1 (72 lines)
