# core/mapping_generator.py
# Purpose: Generate, save, and load Phase E best-config mapping files from fitness results.
# API's: build_mapping_set, save_mapping_set, load_mapping_set
# Notes: Pure Phase E module; operates on generic fitness records and does not depend on GUI.

"""Mapping generator for Phase E best-config JSON artifacts.

This module implements the core logic for Phase E.2:

- Take fitness results (already computed by Phase D / asset_fitness).
- Apply deterministic selection rules to choose a best configuration per
  (asset, timeframe, regime, strategy).
- Produce an in-memory mapping_set dict that conforms to the locked
  JSON schema from project.txt (Phase E Artifact – Exact JSON Schema).
- Provide helpers to save and load mapping files under results/.

Design goals:
- No direct dependency on GUI or CLI.
- No assumptions about how fitness is computed; the caller supplies
  a list of fitness records in a documented structure.
- Selection rules are explicit, deterministic, and easily overridden.
- The JSON schema is treated as canonical; this module is responsible
  for writing it correctly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


# ----------------------------
# Data structures and types
# ----------------------------

@dataclass(frozen=True)
class SelectionRules:
    """Selection thresholds and scoring weights for best-config choice.

    All thresholds are applied *per (asset, timeframe, regime, strategy)*
    group before selecting the best configuration.
    """

    min_trades: int = 50
    min_expectancy_R: float = 0.0
    min_stability_score: float = 0.0
    # max_dd_pct is negative; e.g. -30.0 means 30% drawdown.
    max_dd_pct: float = -100.0

    # Weight for composite score = expectancy_R * stability_score * score_weight.
    score_weight: float = 1.0


FitnessRecord = Mapping[str, Any]
MappingSet = Dict[str, Any]
BestConfig = Dict[str, Any]


# ----------------------------
# Public API
# ----------------------------

def build_mapping_set(
    fitness_records: Iterable[FitnessRecord],
    *,
    rules: Optional[SelectionRules] = None,
    sdl_schema_version: str = "1.0",
    generated_from: str = "",
    description: str = "",
) -> MappingSet:
    """Build a mapping_set dict that conforms to the Phase E JSON schema.

    Parameters
    ----------
    fitness_records:
        Iterable of fitness records. Each record is expected to contain at least:
        - asset: str
        - timeframe: str
        - regime: str
        - strategy_id: str
        - strategy_name: str
        - risk_model: dict
        - performance_snapshot: dict
          (with keys: total_return_pct, winrate_pct, expectancy_R,
           max_dd_pct, total_trades, stability_score)
        Optional keys:
        - overrides: dict (already-computed patch vs base strategy JSON)
        - source_id: str (used for generated_from if provided)

    rules:
        SelectionRules instance describing thresholds and scoring behavior.
        If None, sensible defaults are used.

    sdl_schema_version:
        Value to place in the mapping file's "sdl_schema_version" field.

    generated_from:
        Human-readable identifier for the source fitness run
        (e.g. CSV filename, run id). If empty, we try to infer it from
        the first record with a "source_id" key.

    description:
        Optional human-readable description for the mapping file.

    Returns
    -------
    mapping_set: dict
        A dictionary ready to be serialized as JSON that conforms to the
        locked Phase E schema in project.txt.
    """
    records_list: List[FitnessRecord] = list(fitness_records)
    if not records_list:
        return {
            "schema_version": "1.0",
            "sdl_schema_version": sdl_schema_version,
            "generated_at": _utc_now_iso(),
            "generated_from": generated_from or "",
            "description": description,
            "mappings": [],
        }

    # Infer generated_from if not provided
    if not generated_from:
        for rec in records_list:
            source_id = rec.get("source_id")
            if isinstance(source_id, str) and source_id:
                generated_from = source_id
                break

    rules = rules or SelectionRules()

    best_configs: List[BestConfig] = _select_best_configs(records_list, rules)

    mapping_set: MappingSet = {
        "schema_version": "1.0",
        "sdl_schema_version": sdl_schema_version,
        "generated_at": _utc_now_iso(),
        "generated_from": generated_from,
        "description": description,
        "mappings": best_configs,
    }
    return mapping_set


def save_mapping_set(
    mapping_set: MappingSet,
    tag: Optional[str] = None,
    base_dir: str = "results",
) -> str:
    """Save a mapping_set dict as a JSON file under base_dir.

    The filename follows the convention:

        best_configs_<tag>_<YYYYMMDD_HHMMSS>.json

    where <tag> is omitted if None or empty.

    Parameters
    ----------
    mapping_set:
        The mapping_set dictionary produced by build_mapping_set.

    tag:
        Optional tag describing the run (e.g. "btc_eth_1h").

    base_dir:
        Directory where the file will be written. Defaults to "results".

    Returns
    -------
    path: str
        The full path to the saved JSON file.
    """
    os.makedirs(base_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag_part = f"{tag}_" if tag else ""
    filename = f"best_configs_{tag_part}{timestamp}.json"
    path = os.path.join(base_dir, filename)

    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(mapping_set, f, indent=2, sort_keys=False)

    return path


def load_mapping_set(path: str) -> MappingSet:
    """Load and lightly validate a mapping_set JSON file.

    Parameters
    ----------
    path:
        Path to a JSON file previously produced by save_mapping_set.

    Returns
    -------
    mapping_set: dict

    Raises
    ------
    ValueError
        If required top-level keys are missing or malformed.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _validate_mapping_set(data)
    return data


# ----------------------------
# Internal helpers
# ----------------------------

def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with 'Z' suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _group_key(rec: FitnessRecord) -> Tuple[str, str, str, str]:
    """Return a grouping key for a fitness record.

    We group by (asset, timeframe, regime, strategy_id) to choose the
    best configuration per combination.
    """
    try:
        asset = str(rec["asset"])
        timeframe = str(rec["timeframe"])
        regime = str(rec["regime"])
        strategy_id = str(rec["strategy_id"])
    except KeyError as exc:
        raise KeyError(f"Missing required key in fitness record: {exc}") from exc
    return asset, timeframe, regime, strategy_id


def _select_best_configs(
    records: List[FitnessRecord],
    rules: SelectionRules,
) -> List[BestConfig]:
    """Apply thresholds and scoring to select best configs per group."""
    # Group records
    groups: Dict[Tuple[str, str, str, str], List[FitnessRecord]] = {}
    for rec in records:
        key = _group_key(rec)
        groups.setdefault(key, []).append(rec)

    best_configs: List[BestConfig] = []

    for key, group_records in groups.items():
        # Apply thresholds and compute scores
        candidates: List[Tuple[float, FitnessRecord]] = []
        for rec in group_records:
            perf = rec.get("performance_snapshot") or {}
            try:
                total_trades = int(perf.get("total_trades", 0))
                expectancy_R = float(perf.get("expectancy_R", 0.0))
                max_dd_pct = float(perf.get("max_dd_pct", 0.0))
                stability_score = float(perf.get("stability_score", 0.0))
            except (TypeError, ValueError):
                # Skip malformed record
                continue

            if total_trades < rules.min_trades:
                continue
            if expectancy_R < rules.min_expectancy_R:
                continue
            if stability_score < rules.min_stability_score:
                continue
            # max_dd_pct is negative; e.g. -30.0 is worse than -20.0
            if max_dd_pct < rules.max_dd_pct:
                continue

            composite_score = expectancy_R * max(stability_score, 0.0) * rules.score_weight

            candidates.append((composite_score, rec))

        if not candidates:
            # No valid candidates for this group; skip silently.
            continue

        # Sort by composite score descending; tie-breakers applied via secondary key
        # (higher trades, less severe drawdown).
        def sort_key(item: Tuple[float, FitnessRecord]) -> Tuple[float, int, float]:
            score, rec = item
            perf = rec.get("performance_snapshot") or {}
            total_trades = int(perf.get("total_trades", 0))
            max_dd_pct = float(perf.get("max_dd_pct", 0.0))
            return (
                score,
                total_trades,
                max_dd_pct,  # less negative (higher) is better
            )

        candidates.sort(key=sort_key, reverse=True)
        _, best_rec = candidates[0]

        best_configs.append(_build_best_config(best_rec))

    return best_configs


def _build_best_config(rec: FitnessRecord) -> BestConfig:
    """Build a BestConfig dict from a single fitness record.

    This enforces the field names and nesting required by the locked
    Phase E JSON schema.
    """
    asset = str(rec["asset"])
    timeframe = str(rec["timeframe"])
    regime = str(rec["regime"])
    strategy_id = str(rec["strategy_id"])
    strategy_name = str(rec.get("strategy_name", strategy_id))

    risk_model = rec.get("risk_model") or {}
    if not isinstance(risk_model, dict):
        raise ValueError("fitness record risk_model must be a dict")

    performance_snapshot = rec.get("performance_snapshot") or {}
    if not isinstance(performance_snapshot, dict):
        raise ValueError("fitness record performance_snapshot must be a dict")

    overrides = rec.get("overrides") or {}
    if overrides and not isinstance(overrides, dict):
        raise ValueError("fitness record overrides must be a dict if present")

    live_settings = rec.get("live_settings") or {}
    if not isinstance(live_settings, dict):
        raise ValueError("fitness record live_settings must be a dict if present")

    best: BestConfig = {
        "asset": asset,
        "timeframe": timeframe,
        "regime": regime,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "risk_model": dict(risk_model),
        "performance_snapshot": dict(performance_snapshot),
    }

    if overrides:
        best["overrides"] = dict(overrides)

    # live_settings is optional; we include it if non-empty.
    if live_settings:
        best["live_settings"] = dict(live_settings)

    return best


def _validate_mapping_set(data: Any) -> None:
    """Light validation for loaded mapping_set structures."""
    if not isinstance(data, dict):
        raise ValueError("mapping_set must be a JSON object")

    for key in ("schema_version", "generated_at", "mappings"):
        if key not in data:
            raise ValueError(f"mapping_set is missing required key: {key}")

    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("mapping_set.mappings must be a list")

    for idx, m in enumerate(mappings):
        if not isinstance(m, dict):
            raise ValueError(f"mapping at index {idx} must be an object")
        for key in ("asset", "timeframe", "regime", "strategy_id", "strategy_name", "risk_model", "performance_snapshot"):
            if key not in m:
                raise ValueError(f"mapping at index {idx} missing required key: {key}")
# core/mapping_generator.py v0.1 (372 lines)
