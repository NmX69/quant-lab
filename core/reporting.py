# core/reporting.py
# Purpose: Compute advanced analytics (expectancy, volatility, streaks, Sortino, MAR, regime stats) and export reports.
# Major APIs: build_report, export_report_json, export_report_csv
# Notes: Consumes BacktestResult + TradeLog list; does not depend on GUI or config paths.

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from typing import Dict, Any, List

import numpy as np
import pandas as pd

from core.results import BacktestResult, TradeLog


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if isinstance(x, Decimal):
            return float(x)
        return float(x)
    except Exception:
        return default


def _trade_returns(trades: List[TradeLog]) -> np.ndarray:
    """
    Return per-trade returns as decimal fractions (e.g., +0.01 for +1%).
    Uses pnl_pct if available; falls back to pnl / exposure approximation.
    """
    vals: List[float] = []
    for t in trades:
        # pnl_pct is stored as Decimal percentage
        if hasattr(t, "pnl_pct") and t.pnl_pct is not None:
            vals.append(_safe_float(t.pnl_pct) / 100.0)
        else:
            # Fallback: treat pnl_R as approximate return if no pct
            if hasattr(t, "pnl_R") and t.pnl_R is not None:
                vals.append(float(t.pnl_R))  # This is ugly but better than dropping data
    return np.array(vals, dtype=float) if vals else np.array([], dtype=float)


def _trade_R_values(trades: List[TradeLog]) -> np.ndarray:
    """
    Return per-trade R-multiples (pnl_R).
    """
    vals: List[float] = []
    for t in trades:
        if hasattr(t, "pnl_R") and t.pnl_R is not None:
            vals.append(float(t.pnl_R))
    return np.array(vals, dtype=float) if vals else np.array([], dtype=float)


def _compute_expectancy_R(trades: List[TradeLog]) -> Dict[str, Any]:
    R = _trade_R_values(trades)
    if R.size == 0:
        return {
            "expectancy_R": 0.0,
            "avg_R_win": 0.0,
            "avg_R_loss": 0.0,
            "winrate": 0.0,
            "lossrate": 0.0,
        }

    wins = R[R > 0]
    losses = R[R < 0]

    winrate = float(wins.size) / float(R.size) if R.size else 0.0
    lossrate = float(losses.size) / float(R.size) if R.size else 0.0

    avg_R_win = float(wins.mean()) if wins.size else 0.0
    avg_R_loss = float(losses.mean()) if losses.size else 0.0  # negative

    expectancy_R = winrate * avg_R_win + lossrate * avg_R_loss

    return {
        "expectancy_R": expectancy_R,
        "avg_R_win": avg_R_win,
        "avg_R_loss": avg_R_loss,
        "winrate": winrate * 100.0,
        "lossrate": lossrate * 100.0,
    }


def _compute_volatility_and_sortino(trades: List[TradeLog]) -> Dict[str, Any]:
    r = _trade_returns(trades)
    if r.size == 0:
        return {
            "mean_return_pct": 0.0,
            "volatility_pct": 0.0,
            "sortino": 0.0,
        }

    mean_r = float(r.mean())
    vol_r = float(r.std(ddof=1)) if r.size > 1 else 0.0

    downside = r[r < 0]
    if downside.size > 0:
        downside_dev = float(np.sqrt(np.mean(downside ** 2)))
    else:
        downside_dev = 0.0

    sortino = mean_r / downside_dev if downside_dev > 0 else 0.0

    return {
        "mean_return_pct": mean_r * 100.0,
        "volatility_pct": vol_r * 100.0,
        "sortino": sortino,
    }


def _compute_mar(result: BacktestResult, trades: List[TradeLog]) -> float:
    """
    Compute MAR = CAGR / max_drawdown_abs_fraction.

    - CAGR is based on first and last trade timestamps.
    - If period < 1 month or timestamps are missing, MAR is approximated or 0.
    """
    if not trades:
        return 0.0

    try:
        start_ts = pd.to_datetime(trades[0].entry_ts)
        end_ts = pd.to_datetime(trades[-1].exit_ts)
        days = (end_ts - start_ts).days
        if days <= 0:
            return 0.0
        years = days / 365.25
    except Exception:
        return 0.0

    start_equity = float(result.equity_curve[0]) if result.equity_curve else 100.0
    final_equity = _safe_float(result.final_equity, start_equity)
    if start_equity <= 0 or final_equity <= 0:
        return 0.0

    cagr = (final_equity / start_equity) ** (1.0 / years) - 1.0
    max_dd_frac = abs(_safe_float(result.max_dd_pct, 0.0)) / 100.0
    if max_dd_frac <= 0:
        return 0.0

    return float(cagr / max_dd_frac)


def _compute_streaks(trades: List[TradeLog]) -> Dict[str, int]:
    """
    Compute longest consecutive win and loss streaks based on pnl sign.
    """
    longest_win = 0
    longest_loss = 0
    current_win = 0
    current_loss = 0

    for t in trades:
        pnl = _safe_float(t.pnl, 0.0)
        if pnl > 0:
            current_win += 1
            current_loss = 0
        elif pnl < 0:
            current_loss += 1
            current_win = 0
        else:
            # flat trade breaks both streaks
            current_win = 0
            current_loss = 0

        longest_win = max(longest_win, current_win)
        longest_loss = max(longest_loss, current_loss)

    return {
        "longest_win_streak": int(longest_win),
        "longest_loss_streak": int(longest_loss),
    }


def _compute_drawdown_curve(result: BacktestResult) -> Dict[str, Any]:
    """
    Convert equity_curve into a drawdown curve (fractional and percent).
    """
    equity = [float(e) for e in result.equity_curve] if result.equity_curve else []
    if not equity:
        return {
            "dd_curve_frac": [],
            "dd_curve_pct": [],
        }

    peak = equity[0]
    dd_frac: List[float] = []
    for v in equity:
        peak = max(peak, v)
        dd = (v / peak) - 1.0
        dd_frac.append(dd)

    dd_pct = [x * 100.0 for x in dd_frac]
    return {
        "dd_curve_frac": dd_frac,
        "dd_curve_pct": dd_pct,
    }


def _compute_regime_breakdown(result: BacktestResult) -> Dict[str, Any]:
    """
    Build regime-level stats: trades, winrate, pnl, pnl_pct, expectancy_R per regime.
    """
    regimes: Dict[str, Any] = {}
    trades_by_regime: Dict[str, List[TradeLog]] = {}

    for t in result.trades:
        reg = getattr(t, "regime", "unknown")
        trades_by_regime.setdefault(reg, []).append(t)

    start_equity = float(result.equity_curve[0]) if result.equity_curve else 100.0

    all_regimes = set(result.regime_counts.keys()) | set(trades_by_regime.keys())
    for reg in all_regimes:
        trades = trades_by_regime.get(reg, [])
        pnl_total = _safe_float(result.regime_pnl.get(reg, Decimal("0")), 0.0)
        pnl_pct = (pnl_total / start_equity * 100.0) if start_equity > 0 else 0.0

        R = _trade_R_values(trades)
        wins = R[R > 0]
        losses = R[R < 0]
        n_trades = int(R.size)
        winrate = float(wins.size) / float(R.size) * 100.0 if R.size else 0.0
        lossrate = float(losses.size) / float(R.size) * 100.0 if R.size else 0.0
        avg_R_win = float(wins.mean()) if wins.size else 0.0
        avg_R_loss = float(losses.mean()) if losses.size else 0.0
        expectancy_R = (
            (winrate / 100.0) * avg_R_win + (lossrate / 100.0) * avg_R_loss
            if R.size
            else 0.0
        )

        regimes[reg] = {
            "candles": int(result.regime_counts.get(reg, 0)),
            "pnl": pnl_total,
            "pnl_pct": pnl_pct,
            "trades": n_trades,
            "winrate": winrate,
            "lossrate": lossrate,
            "expectancy_R": expectancy_R,
            "avg_R_win": avg_R_win,
            "avg_R_loss": avg_R_loss,
        }

    return regimes


def build_report(result: BacktestResult) -> Dict[str, Any]:
    """
    Build a structured analytics report from a BacktestResult.
    This is Phase B's core output: everything else is formatting/export.
    """
    trades = result.trades or []

    # Core expectancy and risk metrics
    exp = _compute_expectancy_R(trades)
    vol = _compute_volatility_and_sortino(trades)
    mar = _compute_mar(result, trades)
    streaks = _compute_streaks(trades)
    dd = _compute_drawdown_curve(result)
    regimes = _compute_regime_breakdown(result)

    report: Dict[str, Any] = {
        "meta": {
            "asset": result.asset,
            "mode": result.mode,
            "final_equity": _safe_float(result.final_equity),
            "total_return_pct": _safe_float(result.total_return_pct),
            "total_trades": int(result.total_trades),
            "winrate": float(result.winrate),
            "sharpe": float(result.sharpe),
            "max_dd": _safe_float(result.max_dd),
            "max_dd_pct": _safe_float(result.max_dd_pct),
            "regime_changes": int(result.regime_changes),
        },
        "risk": {
            "expectancy_R": exp["expectancy_R"],
            "avg_R_win": exp["avg_R_win"],
            "avg_R_loss": exp["avg_R_loss"],
            "winrate_pct": exp["winrate"],
            "lossrate_pct": exp["lossrate"],
            "mean_return_pct": vol["mean_return_pct"],
            "volatility_pct": vol["volatility_pct"],
            "sortino": vol["sortino"],
            "mar": mar,
        },
        "streaks": streaks,
        "drawdown": {
            "max_dd_pct": _safe_float(result.max_dd_pct),
            "dd_curve_frac": dd["dd_curve_frac"],
            "dd_curve_pct": dd["dd_curve_pct"],
        },
        "regimes": regimes,
    }

    return report


def export_report_json(report: Dict[str, Any], filepath: str) -> None:
    """
    Export report dict to a JSON file.
    """
    # Convert Decimals and other non-serializable types
    def _convert(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, np.generic):
            return obj.item()
        if hasattr(obj, "__dict__"):
            return asdict(obj)
        return obj

    with open(filepath, "w") as f:
        json.dump(report, f, default=_convert, indent=2)


def export_report_csv(report: Dict[str, Any], filepath: str) -> None:
    """
    Export a flattened view of the report to CSV.
    - Overall metrics in one row.
    - One row per regime with prefix 'regime_<name>_'.
    """
    rows: List[Dict[str, Any]] = []

    # Overall
    overall = {
        "section": "overall",
    }
    for k, v in report.get("meta", {}).items():
        overall[f"meta_{k}"] = v
    for k, v in report.get("risk", {}).items():
        overall[f"risk_{k}"] = v
    for k, v in report.get("streaks", {}).items():
        overall[f"streaks_{k}"] = v
    rows.append(overall)

    # Per-regime rows
    regimes = report.get("regimes", {})
    for name, stats in regimes.items():
        row = {"section": f"regime_{name}"}
        for k, v in stats.items():
            row[f"regime_{k}"] = v
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(filepath, index=False)

# core/reporting.py v0.1 (351 lines)
