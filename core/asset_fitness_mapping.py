# core/asset_fitness_mapping.py
# Purpose: Helpers to convert asset fitness results into Phase E fitness_records.
# API's: build_fitness_records_for_mapping
# Notes: Thin adapter over Phase D outputs; does not change any fitness behavior.

"""Adapters between Phase D asset fitness outputs and Phase E mapping generator.

This module is intentionally conservative: it does not import or modify
core.asset_fitness internals. Instead, it provides helpers that accept
generic fitness result rows and transform them into the `fitness_records`
structure expected by `core.mapping_generator.build_mapping_set`.

The expected input is a sequence of dict-like rows; the calling code is
responsible for extracting these from whatever structure `core.asset_fitness`
currently returns.

Each input row should contain at least:

- asset: str
- timeframe: str
- regime: str
- strategy_id: str
- strategy_name: str or None
- total_trades: int
- total_return_pct: float
- winrate_pct: float
- expectancy_R: float
- max_dd_pct: float (negative for drawdown, e.g. -22.1)
- stability_score: float
- risk_model: dict (the risk config used for this run)
- overrides: dict (optional; patch vs base strategy JSON)

If your actual fitness structure uses different key names, adapt them
before calling this helper, or wrap this function in a small adapter.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


FitnessRow = Mapping[str, Any]
FitnessRecord = Dict[str, Any]


def _to_int(value: Any, default: int = 0) -> int:
    """Best-effort int conversion; fall back to default on failure."""
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def _to_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion; fall back to default on failure."""
    try:
        return float(value)
    except Exception:
        return default


def build_fitness_records_for_mapping(
    rows: Iterable[FitnessRow],
    *,
    source_id: str = "",
    hellmoon_compatible: bool | None = None,
) -> List[FitnessRecord]:
    """Convert generic fitness rows into Phase E fitness_records.

    Parameters
    ----------
    rows:
        Iterable of fitness rows, each a dict-like object with the keys
        described in the module docstring.

    source_id:
        Optional identifier describing the source of these rows
        (e.g. a CSV filename, CLI run label, or GUI session id). If
        provided, it is attached to each record and can later be used
        by `core.mapping_generator.build_mapping_set` as `generated_from`.

    hellmoon_compatible:
        Optional flag to set `live_settings.hellmoon_compatible` in each
        record. If None, `live_settings` is omitted from the record.
        If True or False, a live_settings dict is included with that
        value.

    Returns
    -------
    fitness_records: list of dict
        Each dict is suitable for passing to
        `core.mapping_generator.build_mapping_set`.
    """
    records: List[FitnessRecord] = []

    for row in rows:
        asset = str(row.get("asset", "")).strip()
        timeframe = str(row.get("timeframe", "")).strip()
        regime = str(row.get("regime", "")).strip()
        strategy_id = str(row.get("strategy_id", "")).strip()
        strategy_name_raw = row.get("strategy_name", "") or strategy_id
        strategy_name = str(strategy_name_raw)

        if not asset or not timeframe or not regime or not strategy_id:
            # Skip incomplete rows silently; the caller can log if needed.
            continue

        total_trades = _to_int(row.get("total_trades", 0))
        total_return_pct = _to_float(row.get("total_return_pct", 0.0))
        winrate_pct = _to_float(row.get("winrate_pct", 0.0))
        expectancy_R = _to_float(row.get("expectancy_R", 0.0))
        max_dd_pct = _to_float(row.get("max_dd_pct", 0.0))
        stability_score = _to_float(row.get("stability_score", 0.0))

        risk_model = row.get("risk_model") or {}
        if not isinstance(risk_model, dict):
            # Risk model must be a dict for Phase E
            continue

        overrides = row.get("overrides") or {}
        if overrides and not isinstance(overrides, dict):
            # Overrides, if supplied, must be a dict
            overrides = {}

        performance_snapshot = {
            "total_return_pct": total_return_pct,
            "winrate_pct": winrate_pct,
            "expectancy_R": expectancy_R,
            "max_dd_pct": max_dd_pct,
            "total_trades": total_trades,
            "stability_score": stability_score,
        }

        record: FitnessRecord = {
            "asset": asset,
            "timeframe": timeframe,
            "regime": regime,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "risk_model": risk_model,
            "performance_snapshot": performance_snapshot,
        }

        if overrides:
            record["overrides"] = overrides

        if source_id:
            record["source_id"] = source_id

        if hellmoon_compatible is not None:
            record["live_settings"] = {"hellmoon_compatible": bool(hellmoon_compatible)}

        records.append(record)

    return records
# core/asset_fitness_mapping.py v0.2 (144 lines)
