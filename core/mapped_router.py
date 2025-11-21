# core/mapped_router.py
# Purpose: Provide mapping-aware strategy selection and override application for Phase E.
# APIs: load_mapping_set, MappingIndex, apply_overrides_to_strategy, resolve_mapped_strategy_config
# Notes: Pure core helper; used by backtest_runner and Phase E tooling.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import json
import os


def load_mapping_set(path: str) -> Dict[str, Any]:
    """Load a Phase E best-config mapping file from JSON.

    The file is expected to follow the locked schema documented in the
    project plan:

        {
          "schema_version": "1.0",
          "sdl_schema_version": "1.0",
          "generated_at": "...",
          "generated_from": "...",
          "description": "...",
          "mappings": [
            {
              "asset": "BTCUSDT",
              "timeframe": "1h",
              "regime": "balanced",
              "strategy_id": "trend_macd",
              ...
            }
          ]
        }
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Mapping file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Mapping file must be a JSON object at the top level.")

    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("Mapping file is missing a 'mappings' list.")

    return data


class MappingIndex:
    """Index helper over a mapping_set["mappings"] list.

    Keys are normalized to strings:
        (asset, timeframe, regime) -> mapping-entry dict
    """

    def __init__(self, mapping_set: Dict[str, Any]) -> None:
        self.mapping_set = mapping_set
        self._index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._build_index()

    def _build_index(self) -> None:
        mappings = self.mapping_set.get("mappings", [])
        if not isinstance(mappings, list):
            return

        for entry in mappings:
            if not isinstance(entry, dict):
                continue

            asset = str(entry.get("asset", "")).strip()
            timeframe = str(entry.get("timeframe", "")).strip()
            regime = str(entry.get("regime", "")).strip()

            if not asset or not timeframe or not regime:
                continue

            key = (asset, timeframe, regime)
            self._index[key] = entry

    def get_entry(self, asset: str, timeframe: str, regime: str) -> Optional[Dict[str, Any]]:
        """Return the mapping entry for (asset, timeframe, regime), or None."""
        key = (str(asset), str(timeframe), str(regime))
        return self._index.get(key)

    def build_regime_strategy_map(self, asset: str, timeframe: str) -> Dict[str, str]:
        """Return a regime->strategy_id mapping for a given asset/timeframe.

        If the mapping set defines multiple explicit regimes for this
        asset/timeframe (e.g. 'trending_up', 'trending_down', 'ranging'), we
        preserve them as-is.

        If it only defines a single 'default-style' regime such as
        'balanced', we expand that to a reasonable set of router regimes so
        that the router never sees an unmapped regime like 'trending_up'.
        """
        asset_s = str(asset)
        timeframe_s = str(timeframe)

        # First, collect the raw regime->strategy_id from the mapping set.
        raw: Dict[str, str] = {}
        for (a, tf, regime), entry in self._index.items():
            if a == asset_s and tf == timeframe_s:
                sid = entry.get("strategy_id")
                if isinstance(sid, str):
                    raw[str(regime)] = sid

        if not raw:
            return {}

        # If we already have multiple explicit regimes, or any regime name
        # that is not a simple 'balanced'/'default' bucket, just return the
        # raw mapping unchanged.
        non_default = [r for r in raw if r not in ("balanced", "default", "all")]
        if len(raw) > 1 or non_default:
            return raw

        # Otherwise, treat the single entry as a default-for-all router
        # regimes (e.g. a basic 'balanced' configuration that should run
        # regardless of short-term trend label).
        sid = next(iter(raw.values()))
        expanded: Dict[str, str] = {
            "balanced": sid,
            "trending_up": sid,
            "trending_down": sid,
            "ranging": sid,
        }
        return expanded


def _split_path_segment(segment: str) -> Tuple[str, Optional[int]]:
    """Split a single override path segment into (name, index).

    Examples:
        "conditions[0]" -> ("conditions", 0)
        "rsi_period"    -> ("rsi_period", None)
    """
    if "[" in segment and segment.endswith("]"):
        name, idx_str = segment.split("[", 1)
        idx_str = idx_str[:-1]  # drop closing ]
        try:
            idx = int(idx_str)
        except ValueError:
            idx = None
        return name, idx
    return segment, None


def _apply_single_override(target: Dict[str, Any], path: str, value: Any) -> None:
    """Apply a single override like 'entry.conditions[0].rsi_period' = 25."""
    if not path:
        return

    segments = [seg for seg in path.split(".") if seg]
    current: Any = target

    for i, seg in enumerate(segments):
        name, idx = _split_path_segment(seg)
        is_last = i == len(segments) - 1

        if idx is None:
            # Dict-like access
            if not isinstance(current, dict):
                return
            if is_last:
                current[name] = value
                return
            if name not in current or not isinstance(current[name], (dict, list)):
                current[name] = {}
            current = current[name]
        else:
            # List-like access
            if not isinstance(current, dict):
                return
            if name not in current or not isinstance(current[name], list):
                current[name] = []
            lst = current[name]
            while len(lst) <= idx:
                lst.append({})
            if is_last:
                lst[idx] = value
                return
            if not isinstance(lst[idx], dict):
                lst[idx] = {}
            current = lst[idx]


def apply_overrides_to_strategy(
    base_strategy: Dict[str, Any],
    overrides: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a deep-copied strategy dict with overrides applied.

    Overrides follow the path grammar used in the Phase E JSON:
        "entry.conditions[0].rsi_period": 25
        "exit.take_profit_rr": 2.5
    """
    if not overrides:
        # Shallow clone is fine if we don't mutate
        return json.loads(json.dumps(base_strategy))

    # Deep copy via JSON round-trip (strategies are JSON-compatible)
    result: Dict[str, Any] = json.loads(json.dumps(base_strategy))

    for path, value in overrides.items():
        if not isinstance(path, str):
            continue
        _apply_single_override(result, path, value)

    return result


def resolve_mapped_strategy_config(
    base_strategy: Dict[str, Any],
    mapping_entry: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply the mapping entry's overrides to the base strategy.

    This does *not* touch risk_model or live_settings; those are handled
    by the caller (e.g. backtest_runner or a future live engine).
    """
    overrides = mapping_entry.get("overrides") or {}
    if not isinstance(overrides, dict):
        overrides = {}

    return apply_overrides_to_strategy(base_strategy, overrides)

# core/mapped_router.py v0.2 (231 lines)
