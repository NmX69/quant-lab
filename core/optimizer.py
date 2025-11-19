# core/optimizer.py
# Purpose: Public façade for optimizer functionality (engine-level and strategy-level grid searches + region filters).
# Major External Functions/Classes:
#   - grid_search_single_asset
#   - grid_search_all_assets
#   - grid_search_strategy_params_single_asset
#   - select_good_region
#   - summarize_region
# Notes: Thin wrapper that re-exports functions from optimizer_* modules after Phase C refactor.

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from core.optimizer_engine import (
    grid_search_single_asset,
    grid_search_all_assets,
)
from core.optimizer_strategy import (
    grid_search_strategy_params_single_asset,
)
from core.optimizer_region import (
    select_good_region,
    summarize_region,
)

__all__ = [
    "grid_search_single_asset",
    "grid_search_all_assets",
    "grid_search_strategy_params_single_asset",
    "select_good_region",
    "summarize_region",
]

# core/optimizer.py v0.5 (37 lines)
