# core/optimizer_strategy.py
# Purpose: Strategy-level parameter grid search (C3).
# Major External Functions/Classes:
#   - grid_search_strategy_params_single_asset
# Notes: Applies dotted-path overrides to strategy JSON definitions.

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Optional

import pandas as pd

from core.engine import run_backtest
from core.optimizer_common import _load_and_prepare_df
from core.strategy_loader import get_strategy
import core.strategy_loader as strategy_loader_mod


def _apply_path_override(target: Dict[str, Any], path: str, value: Any) -> None:
    """
    Apply a single override into a nested strategy dict using a simple dotted path syntax.

    Example paths:
        "entry.conditions[1].below"
        "exit.stop_loss"
        "exit.take_profit"
        "risk.risk_per_trade_pct"

    Indexing syntax: "conditions[0]" is supported on list-valued keys.
    """
    parts = path.split(".")
    current: Any = target

    for i, raw in enumerate(parts):
        # Handle list indexing like "conditions[1]"
        if "[" in raw and raw.endswith("]"):
            key, idx_str = raw.split("[", 1)
            idx = int(idx_str[:-1])

            if key not in current or not isinstance(current[key], list):
                raise KeyError(f"Path '{path}' invalid at segment '{raw}'")

            lst = current[key]
            if i == len(parts) - 1:
                # Final segment: assign into list element
                if idx < 0 or idx >= len(lst):
                    raise IndexError(f"Index {idx} out of range for '{raw}' in path '{path}'")
                lst[idx] = value
                return

            # Intermediate segment: descend into list element
            if idx < 0 or idx >= len(lst):
                raise IndexError(f"Index {idx} out of range for '{raw}' in path '{path}'")
            current = lst[idx]
        else:
            # Normal dict key
            if i == len(parts) - 1:
                current[raw] = value
                return

            if raw not in current or not isinstance(current[raw], (dict, list)):
                # If the intermediate node is missing, create a dict subtree
                current[raw] = {}
            current = current[raw]


def _apply_strategy_overrides(base_strategy: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a *new* strategy dict with all overrides applied.

    overrides keys are dotted paths, e.g.:
        {
            "entry.conditions[1].below": 35,
            "exit.stop_loss": "4%",
            "exit.take_profit": "12%",
        }
    """
    from copy import deepcopy

    new_cfg = deepcopy(base_strategy)
    for path, value in overrides.items():
        _apply_path_override(new_cfg, path, value)
    return new_cfg


def _build_strategy_param_combinations(param_grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    Build list of override dicts for strategy-level params.

    param_grid example:
        {
            "entry.conditions[1].below": [30, 35],
            "exit.stop_loss": ["3%", "4%"],
            "exit.take_profit": ["9%", "12%"],
        }

    Returns a list of dicts like:
        [
            {
              "entry.conditions[1].below": 30,
              "exit.stop_loss": "3%",
              "exit.take_profit": "9%",
            },
            {
              "entry.conditions[1].below": 30,
              "exit.stop_loss": "3%",
              "exit.take_profit": "12%",
            },
            ...
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


def grid_search_strategy_params_single_asset(
    asset_file: str,
    strategy_name: str,
    mode: str,
    strategy_param_grid: Dict[str, List[Any]],
    *,
    position_pct: float,
    risk_pct: float,
    reward_rr: float,
    max_candles: int = 0,
) -> pd.DataFrame:
    """
    Grid search over *strategy-level* parameters (JSON fields) for a single asset & strategy.

    Important:
        - This operates in *non-router* mode (use_router=False) intentionally, so the
          behavior of the tested strategy is isolated.
        - Engine-level risk/position params (position_pct, risk_pct, reward_rr) are
          fixed for the entire grid; the idea is you first find a sane risk envelope
          (C1/C2) and then tune the strategy shape (C3).

    Args:
        asset_file: CSV filename under data/ (e.g., "BTCUSDT_1h.csv").
        strategy_name: Strategy key (e.g., "range_mean_reversion").
        mode: "conservative" | "balanced" | "aggressive".
        strategy_param_grid: Dict of dotted-path keys → list of candidate values.
        position_pct, risk_pct, reward_rr: Fixed engine-level envelope.
        max_candles: Optional cap on number of candles.

    Returns:
        DataFrame with one row per strategy-parameter combination, including the
        override values and core performance metrics.
    """
    df = _load_and_prepare_df(asset_file, max_candles)

    # Get a *baseline* strategy definition
    original_strategy = get_strategy(strategy_name)
    if original_strategy is None:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    overrides_list = _build_strategy_param_combinations(strategy_param_grid)

    # We'll temporarily patch the strategy_loader's registry to inject overrides.
    strategies_dict = strategy_loader_mod._STRATEGIES  # type: ignore[attr-defined]

    rows: List[Dict[str, Any]] = []

    for overrides in overrides_list:
        from copy import deepcopy

        # Work off a fresh copy to avoid cross-contamination
        base_cfg = deepcopy(original_strategy)
        overridden = _apply_strategy_overrides(base_cfg, overrides)

        # Replace the global strategy for this name so engine sees it
        strategies_dict[strategy_name] = overridden

        try:
            summary, result = run_backtest(
                df=df,
                mode=mode,
                strategy_name=strategy_name,
                use_router=False,
                strategy_mappings=None,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )

            if result is None:
                continue

            row: Dict[str, Any] = {
                **overrides,
                "final_equity": float(result.final_equity),
                "total_return_pct": float(result.total_return_pct),
                "sharpe": float(result.sharpe),
                "max_dd_pct": float(result.max_dd_pct),
                "total_trades": int(result.total_trades),
                "winrate": float(result.winrate),
            }
            rows.append(row)

        except Exception:
            # Record failed combo with NaNs so we can see that region as "bad"
            row = {
                **overrides,
                "final_equity": float("nan"),
                "total_return_pct": float("nan"),
                "sharpe": float("nan"),
                "max_dd_pct": float("nan"),
                "total_trades": 0,
                "winrate": 0.0,
            }
            rows.append(row)

    # Restore original strategy definition
    strategies_dict[strategy_name] = original_strategy

    if not rows:
        return pd.DataFrame()

    df_res = pd.DataFrame(rows)
    df_res = df_res.sort_values(
        by=["total_return_pct", "sharpe"],
        ascending=[False, False],
        ignore_index=True,
    )
    return df_res

# core/optimizer_strategy.py v0.1 (237 lines)
