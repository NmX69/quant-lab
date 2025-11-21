# core/asset_fitness.py
# Purpose: Compute strategy × asset fitness metrics (expectancy, regime stats, stability scores) with no GUI dependencies.
# Major External Functions/Classes:
#   - run_fitness_for_strategy
#   - run_fitness_matrix
#   - compute_stability_metrics
#   - rank_assets_for_strategy
#   - export_fitness_matrix
# Notes: Builds on core.engine, core.optimizer_common, core.reporting, and core.results.

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.config_manager import RESULTS_DIR
from core.engine import run_backtest
from core.optimizer_common import _load_manifest_pairs_for_timeframe, _load_and_prepare_df
from core.reporting import build_report


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _safe_float(value: Any) -> float:
    """Convert Decimal/np types to float safely."""
    if value is None:
        return float("nan")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (np.generic,)):
        return float(value)
    try:
        return float(value)
    except Exception:
        return float("nan")


def _ensure_results_dir() -> str:
    """Ensure the fitness results subdirectory exists and return its path."""
    fitness_dir = os.path.join(RESULTS_DIR, "fitness")
    os.makedirs(fitness_dir, exist_ok=True)
    return fitness_dir


# ----------------------------------------------------------------------
# Phase D: Core Fitness Runner
# ----------------------------------------------------------------------

def run_fitness_for_strategy(
    timeframe: str,
    strategy_name: str,
    mode: str,
    use_router: bool,
    max_candles: int,
    strategy_mappings: Optional[Dict[str, str]],
    position_pct: float,
    risk_pct: float,
    reward_rr: Optional[float],
    assets: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Run a single strategy (or router) across all assets for a timeframe.
    Returns a long-format DataFrame with one row per (asset, timeframe).
    """
    manifest_entries = _load_manifest_pairs_for_timeframe(timeframe)

    if assets:
        allowed = set(assets)
        manifest_entries = [m for m in manifest_entries if m.get("pair") in allowed]

    rows: List[Dict[str, Any]] = []

    for entry in manifest_entries:
        pair = entry.get("pair")
        asset_file = entry.get("file")
        candles_available = entry.get("candles")

        try:
            df = _load_and_prepare_df(asset_file, max_candles)

            _, result = run_backtest(
                df=df,
                mode=mode,
                strategy_name=strategy_name,
                use_router=use_router,
                strategy_mappings=strategy_mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )

            if result is None:
                continue

            report = build_report(result)

            risk = report.get("risk", {})
            drawdown = report.get("drawdown", {})
            regimes = report.get("regimes", {}) or {}

            total_candles = int(sum(result.regime_counts.values())) if result.regime_counts else 0

            row: Dict[str, Any] = {
                "strategy_name": strategy_name,
                "asset": pair,
                "timeframe": timeframe,
                "mode": mode,
                "use_router": use_router,
                "position_pct": position_pct,
                "risk_pct": risk_pct,
                "reward_rr": reward_rr,
                "candles_available": candles_available,
                "total_candles": total_candles,
                "final_equity": _safe_float(result.final_equity),
                "total_return_pct": _safe_float(result.total_return_pct),
                "total_trades": int(result.total_trades),
                "winrate": _safe_float(result.winrate),
                "sharpe": _safe_float(result.sharpe),
                "max_dd": _safe_float(result.max_dd),
                "max_dd_pct": _safe_float(result.max_dd_pct),
                "regime_changes": int(result.regime_changes),
                # Core expectancy / risk metrics
                "expectancy_R": _safe_float(risk.get("expectancy_R")),
                "avg_R_win": _safe_float(risk.get("avg_R_win")),
                "avg_R_loss": _safe_float(risk.get("avg_R_loss")),
                "winrate_pct": _safe_float(risk.get("winrate_pct")),
                "lossrate_pct": _safe_float(risk.get("lossrate_pct")),
                "mean_return_pct": _safe_float(risk.get("mean_return_pct")),
                "volatility_pct": _safe_float(risk.get("volatility_pct")),
                "sortino": _safe_float(risk.get("sortino")),
                "mar": _safe_float(risk.get("mar")),
                "max_dd_pct_report": _safe_float(drawdown.get("max_dd_pct")),
            }

            # Per-regime flattening
            for reg_name, stats in regimes.items():
                prefix = f"reg_{reg_name}"

                candles = int(stats.get("candles", 0))
                trades = int(stats.get("trades", 0))

                row[f"{prefix}_candles"] = candles
                row[f"{prefix}_candles_frac"] = (
                    candles / float(total_candles) if total_candles else float("nan")
                )

                row[f"{prefix}_pnl_pct"] = _safe_float(stats.get("pnl_pct"))
                row[f"{prefix}_trades"] = trades
                row[f"{prefix}_winrate"] = _safe_float(stats.get("winrate"))
                row[f"{prefix}_expectancy_R"] = _safe_float(stats.get("expectancy_R"))
                row[f"{prefix}_avg_R_win"] = _safe_float(stats.get("avg_R_win"))
                row[f"{prefix}_avg_R_loss"] = _safe_float(stats.get("avg_R_loss"))

            rows.append(row)

        except Exception:
            continue

    return pd.DataFrame(rows)


def run_fitness_matrix(
    strategies: List[str],
    timeframes: List[str],
    mode: str,
    use_router: bool,
    max_candles: int,
    strategy_mappings: Optional[Dict[str, str]],
    position_pct: float,
    risk_pct: float,
    reward_rr: Optional[float],
    assets: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Run a full Phase-D sweep across strategies × assets × timeframes.
    Returns a long DataFrame.
    """
    frames = []
    for strategy_name in strategies:
        for tf in timeframes:
            df = run_fitness_for_strategy(
                timeframe=tf,
                strategy_name=strategy_name,
                mode=mode,
                use_router=use_router,
                max_candles=max_candles,
                strategy_mappings=strategy_mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
                assets=assets,
            )
            if not df.empty:
                frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ----------------------------------------------------------------------
# Stability Metrics (updated per your request)
# ----------------------------------------------------------------------

def compute_stability_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add:
      - regime_std / regime_cv (with stabilizing epsilon)
      - worst_regime_E
      - trade_density (softened scaling)
      - expectancy_per_dd
      - stability_score (improved)
      - fitness_score (always negative if expectancy_R negative)
    """
    if df.empty:
        return df

    df = df.copy()
    regime_cols = [c for c in df.columns if c.startswith("reg_") and c.endswith("_expectancy_R")]

    EPS_E = 0.10   # epsilon to prevent CV explosion for near-zero expectancy
    EPS_FIT = 1e-6 # avoid zero fitness (keeps sign meaning)

    def _row(row: pd.Series) -> Dict[str, float]:
        E = float(row.get("expectancy_R", float("nan")))

        # ---- Collect per-regime exp values
        exp_vals = []
        for col in regime_cols:
            v = row.get(col)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            exp_vals.append(float(v))

        if exp_vals:
            regime_std = float(np.std(exp_vals))
            worst_regime = float(np.min(exp_vals))
        else:
            regime_std = float("nan")
            worst_regime = float("nan")

        # ---- Stabilized regime_cv
        denom = max(abs(E), EPS_E)
        regime_cv = regime_std / denom

        # ---- Trade density (soft ramp)
        total_trades = float(row.get("total_trades") or 0)
        total_candles = float(row.get("total_candles") or 0)
        trade_density = total_trades / total_candles if total_candles else float("nan")

        # Smooth trade_factor: begins rising at 5 trades, hits full strength ~150
        trade_factor = 0.0
        if total_trades > 5:
            trade_factor = min(1.0, (total_trades - 5.0) / 145.0)

        # ---- DD normalization
        max_dd_pct = row.get("max_dd_pct")
        try:
            max_dd_pct = float(max_dd_pct)
        except Exception:
            max_dd_pct = float("nan")

        if max_dd_pct is None or np.isnan(max_dd_pct):
            expectancy_per_dd = float("nan")
            dd_factor = 1.0
        else:
            dd_abs = abs(max_dd_pct)
            denom_dd = (dd_abs / 100.0) if dd_abs > 0 else 0.0001
            expectancy_per_dd = E / denom_dd

            # drawdown penalty: ~40%+ starts to hurt more
            dd_factor = 1.0 / (1.0 + max(0.0, (dd_abs - 10.0) / 30.0))

        # ---- Base score: still penalizes negative expectancy, but not binary
        if np.isnan(E):
            base_score = 0.0
        else:
            base_score = 1.0 if E > 0 else 0.25

        # ---- Regime stability penalty (bounded now)
        regime_factor = 1.0 / (1.0 + max(0.0, regime_cv))

        # ---- Final stability
        stability = base_score * trade_factor * regime_factor * dd_factor

        # ---- Fitness always preserves sign of expectancy
        if np.isnan(E):
            fitness = 0.0
        else:
            fitness = E * max(stability, EPS_FIT)  # keeps negative combos negative; avoids zero masking

        return {
            "regime_std": regime_std,
            "regime_cv": regime_cv,
            "worst_regime_E": worst_regime,
            "trade_density": trade_density,
            "expectancy_per_dd": expectancy_per_dd,
            "stability_score": stability,
            "fitness_score": fitness,
        }

    metrics = df.apply(_row, axis=1, result_type="expand")
    for col in metrics.columns:
        df[col] = metrics[col]

    return df


# ----------------------------------------------------------------------
# Ranking + Export
# ----------------------------------------------------------------------

def rank_assets_for_strategy(
    df: pd.DataFrame,
    strategy_name: str,
    timeframe: Optional[str] = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    mask = df["strategy_name"] == strategy_name
    if timeframe:
        mask &= df["timeframe"] == timeframe

    sub = df.loc[mask].copy()
    if sub.empty:
        return sub

    sort_cols = [c for c in ("fitness_score", "expectancy_R", "sharpe") if c in sub.columns]
    sub.sort_values(sort_cols, ascending=[False] * len(sort_cols), inplace=True)
    return sub


def export_fitness_matrix(df: pd.DataFrame, tag: str) -> Tuple[str, str]:
    fitness_dir = _ensure_results_dir()
    safe_tag = tag.replace(" ", "_")

    csv_path = os.path.join(fitness_dir, f"fitness_matrix_{safe_tag}.csv")
    json_path = os.path.join(fitness_dir, f"fitness_matrix_{safe_tag}.json")

    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)

    return csv_path, json_path


# core/asset_fitness.py v0.2 (354 lines)
