# core/state.py
# Purpose: Hold backtest state and provide helpers for regime updates, position tracking, and entries.
# Major External Functions/Classes: BacktestState, init_backtest_state, update_regime_for_bar, update_position_tracking_for_bar, maybe_open_position
# Notes: Entry logic and regime bookkeeping extracted from engine v1.7; behavior preserved.

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

import pandas as pd

from core.results import TradeLog
from core.conditions import evaluate_condition, invert_condition
from core.sizing import compute_position_and_stops


@dataclass
class BacktestState:
    capital: Decimal
    position: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    entry_ts: str = ""
    entry_regime: str = ""
    initial_exposure: Decimal = Decimal("0")
    stop_price: Decimal = Decimal("0")
    high_water: Decimal = Decimal("0")
    low_water: Decimal = Decimal("0")
    trailing_active: bool = False
    entry_stop_price: Decimal = Decimal("0")
    entry_stop_distance_pct: float = 0.0
    entry_rr_multiple: float = 0.0
    entry_take_profit_pct: Decimal = Decimal("0")  # per-trade TP pct at entry
    equity: List[Decimal] = field(default_factory=list)
    trades: List[TradeLog] = field(default_factory=list)
    regime_pnl: Dict[str, Decimal] = field(default_factory=dict)
    regime_changes: int = 0
    regime_counts: Dict[str, int] = field(default_factory=dict)
    prev_regime: Optional[str] = None


def init_backtest_state(
    starting_capital: Decimal,
    regime_up_label: str,
    regime_down_label: str,
    regime_range_label: str,
) -> BacktestState:
    state = BacktestState(capital=starting_capital)
    state.equity.append(starting_capital)

    state.regime_pnl = {
        regime_up_label: Decimal("0"),
        regime_down_label: Decimal("0"),
        regime_range_label: Decimal("0"),
    }
    state.regime_counts = {
        regime_up_label: 0,
        regime_down_label: 0,
        regime_range_label: 0,
    }
    state.regime_changes = 0
    state.prev_regime = None
    return state


def update_regime_for_bar(state: BacktestState, current_regime: str) -> None:
    if current_regime != state.prev_regime:
        if state.prev_regime is not None:
            state.regime_changes += 1
        state.prev_regime = current_regime

    state.regime_counts[current_regime] = state.regime_counts.get(current_regime, 0) + 1


def update_position_tracking_for_bar(
    state: BacktestState,
    high: Decimal,
    low: Decimal,
) -> None:
    if state.position == 0:
        return

    is_long = state.position > 0
    if is_long:
        state.high_water = max(state.high_water, high)
        state.low_water = min(state.low_water, low)
    else:
        state.high_water = min(state.high_water, high)
        state.low_water = max(state.low_water, low)


def maybe_open_position(
    state: BacktestState,
    row: pd.Series,
    prev: pd.Series,
    current_strategy: Dict,
    current_regime: str,
    adx_threshold: float,
    sizing: str,
    position_frac: Decimal,
    risk_per_trade_frac: Decimal,
    fixed_rr: Decimal,
    stop_loss_pct_cfg: Decimal,
    take_profit_pct_cfg: Decimal,
    max_exposure_usd: Decimal,
    trailing_stop_pct: Decimal,
    fee_pct: Decimal,
) -> None:
    """
    Entry logic extracted from engine.run_backtest.
    Mutates `state` in-place and appends to equity on entry,
    but only when currently flat (position == 0).
    """
    if state.position != 0:
        return

    entry_conditions = current_strategy["entry"]["conditions"]
    direction = current_strategy["direction"]

    long_entry = all(
        evaluate_condition(c, row, prev, adx_threshold) for c in entry_conditions
    )

    short_entry = False
    if direction in ["short", "both"]:
        short_entry = all(
            evaluate_condition(invert_condition(c), row, prev, adx_threshold)
            for c in entry_conditions
        )

    if direction == "long":
        entry_met = long_entry
        is_long = True
    elif direction == "short":
        entry_met = short_entry
        is_long = False
    else:  # "both"
        entry_met = long_entry or short_entry
        # Original behavior: treat as long by default for now
        is_long = True

    if not entry_met:
        return

    price = Decimal(str(row["close"]))

    position_size, stop_loss_pct, take_profit_pct = compute_position_and_stops(
        capital=state.capital,
        price=price,
        position_frac=position_frac,
        risk_per_trade_frac=risk_per_trade_frac,
        fixed_rr=fixed_rr,
        sizing=sizing,
        stop_loss_pct_cfg=stop_loss_pct_cfg,
        take_profit_pct_cfg=take_profit_pct_cfg,
        max_exposure_usd=max_exposure_usd,
        fee_pct=fee_pct,
    )

    if position_size <= 0 or not position_size.is_finite():
        position_size = Decimal("0.001")

    state.position = position_size if is_long else -position_size
    state.entry_price = price
    state.entry_ts = str(row["timestamp"])
    state.entry_regime = current_regime
    state.initial_exposure = abs(state.position) * price

    state.stop_price = (
        state.entry_price * (Decimal("1") - stop_loss_pct)
        if is_long
        else state.entry_price * (Decimal("1") + stop_loss_pct)
    )
    state.high_water = state.entry_price
    state.low_water = state.entry_price
    state.trailing_active = trailing_stop_pct > 0

    state.entry_stop_price = state.stop_price
    if state.entry_price != 0:
        state.entry_stop_distance_pct = float(
            (abs(state.entry_price - state.stop_price) / state.entry_price) * 100
        )
    else:
        state.entry_stop_distance_pct = 0.0

    # Store per-trade RR + TP pct so exits can use them directly
    state.entry_rr_multiple = float(
        (take_profit_pct / stop_loss_pct) if stop_loss_pct != 0 else fixed_rr
    )
    state.entry_take_profit_pct = take_profit_pct

    state.equity.append(state.capital)

# core/state.py v0.4 (193 lines)
# 