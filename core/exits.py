# core/exits.py
# Purpose: Implement exit logic (TP, SL, trailing, signal) and canonical TradeLog construction.
# Major External Functions/Classes: build_trade, handle_exits_for_bar, close_at_end_of_data
# Notes: Exit behavior preserved from engine v1.7; now operates on BacktestState.

from decimal import Decimal

import pandas as pd

from core.results import TradeLog
from core.conditions import evaluate_condition, invert_condition
from core.state import BacktestState


def build_trade(
    entry_ts: str,
    exit_ts_raw,
    entry_price: Decimal,
    exit_price: Decimal,
    close_amount: Decimal,
    pnl: Decimal,
    entry_regime: str,
    strategy_name: str,
    exit_reason: str,
    is_long: bool,
    initial_exposure: Decimal,
    high_water: Decimal,
    low_water: Decimal,
    entry_stop_price: Decimal,
    fixed_rr: Decimal,
    stop_distance_pct: float,
    take_profit_multiple: float,
) -> TradeLog:
    if is_long:
        mae = ((low_water - entry_price) / entry_price * 100) if entry_price != 0 else Decimal("0")
        mfe = ((high_water - entry_price) / entry_price * 100) if entry_price != 0 else Decimal("0")
    else:
        mae = ((entry_price - high_water) / entry_price * 100) if entry_price != 0 else Decimal("0")
        mfe = ((entry_price - low_water) / entry_price * 100) if entry_price != 0 else Decimal("0")

    pnl_pct = (pnl / initial_exposure) * 100 if initial_exposure else Decimal("0")

    try:
        entry_dt = pd.to_datetime(entry_ts)
        exit_dt = pd.to_datetime(exit_ts_raw)
        hold_time_hours = (exit_dt - entry_dt).total_seconds() / 3600.0
    except Exception:
        hold_time_hours = 0.0

    stop_dist_abs = abs(entry_price - entry_stop_price)
    risk_amount = stop_dist_abs * close_amount if stop_dist_abs > 0 else Decimal("0")
    pnl_R = float(pnl / risk_amount) if risk_amount != 0 else 0.0

    return TradeLog(
        entry_ts=str(entry_ts),
        exit_ts=str(exit_ts_raw),
        entry_price=entry_price,
        exit_price=exit_price,
        position=close_amount if is_long else -close_amount,
        pnl=pnl,
        pnl_pct=pnl_pct,
        regime=entry_regime,
        strategy=strategy_name,
        exit_reason=exit_reason,
        mae=mae,
        mfe=mfe,
        pnl_R=pnl_R,
        reward_multiple=float(fixed_rr),
        stop_distance_pct=float(stop_distance_pct),
        take_profit_multiple=float(take_profit_multiple),
        hold_time_hours=hold_time_hours,
        trade_type="long" if is_long else "short",
    )


def _compute_pnl(
    is_long: bool,
    entry_price: Decimal,
    price: Decimal,
    close_amount: Decimal,
    fee_pct: Decimal,
) -> Decimal:
    fee = fee_pct * (close_amount * price)
    if is_long:
        return (price - entry_price) * close_amount - fee
    return (entry_price - price) * close_amount - fee


def handle_exits_for_bar(
    state: BacktestState,
    row: pd.Series,
    prev: pd.Series,
    current_strategy,
    signal_exit,
    trailing_stop_pct: Decimal,
    fixed_rr: Decimal,
    fee_pct: Decimal,
    adx_threshold: float,
    partial_exit_pct: Decimal,
) -> None:
    """
    Per-bar exit logic:
      1) Take profit
      2) Stop loss (including trailing)
      3) Trailing stop update
      4) Signal-based exit
    """
    if state.position == 0:
        return

    price = Decimal(str(row["close"]))
    is_long = state.position > 0

    # --- 1) TAKE PROFIT ---
    if state.entry_take_profit_pct != 0:
        tp_price = (
            state.entry_price * (Decimal("1") + state.entry_take_profit_pct)
            if is_long
            else state.entry_price * (Decimal("1") - state.entry_take_profit_pct)
        )
    else:
        tp_price = state.entry_price  # no TP configured

    if state.entry_take_profit_pct != 0 and (
        (is_long and price >= tp_price) or (not is_long and price <= tp_price)
    ):
        close_amount = abs(state.position) * (
            partial_exit_pct if partial_exit_pct > 0 else Decimal("1")
        )
        pnl = _compute_pnl(is_long, state.entry_price, price, close_amount, fee_pct)

        state.capital += pnl
        trade = build_trade(
            entry_ts=state.entry_ts,
            exit_ts_raw=row["timestamp"],
            entry_price=state.entry_price,
            exit_price=price,
            close_amount=close_amount,
            pnl=pnl,
            entry_regime=state.entry_regime,
            strategy_name=current_strategy["name"],
            exit_reason="take_profit",
            is_long=is_long,
            initial_exposure=state.initial_exposure,
            high_water=state.high_water,
            low_water=state.low_water,
            entry_stop_price=state.entry_stop_price,
            fixed_rr=fixed_rr,
            stop_distance_pct=state.entry_stop_distance_pct,
            take_profit_multiple=state.entry_rr_multiple,
        )
        state.trades.append(trade)
        state.regime_pnl[state.entry_regime] += pnl

        state.position -= close_amount if is_long else -close_amount
        state.equity.append(state.capital)
        if state.position == 0:
            return

    # Re-evaluate direction if partial exit changed sign (it shouldn't, but keep consistent)
    is_long = state.position > 0

    # --- 2) STOP LOSS (including trailing) ---
    if (is_long and price <= state.stop_price) or (not is_long and price >= state.stop_price):
        close_amount = abs(state.position)
        pnl = _compute_pnl(is_long, state.entry_price, price, close_amount, fee_pct)

        state.capital += pnl
        trade = build_trade(
            entry_ts=state.entry_ts,
            exit_ts_raw=row["timestamp"],
            entry_price=state.entry_price,
            exit_price=price,
            close_amount=close_amount,
            pnl=pnl,
            entry_regime=state.entry_regime,
            strategy_name=current_strategy["name"],
            exit_reason="stop_loss",
            is_long=is_long,
            initial_exposure=state.initial_exposure,
            high_water=state.high_water,
            low_water=state.low_water,
            entry_stop_price=state.entry_stop_price,
            fixed_rr=fixed_rr,
            stop_distance_pct=state.entry_stop_distance_pct,
            take_profit_multiple=state.entry_rr_multiple,
        )
        state.trades.append(trade)
        state.regime_pnl[state.entry_regime] += pnl

        state.equity.append(state.capital)
        state.position = Decimal("0")
        return

    # --- 3) TRAILING STOP ADJUSTMENT ---
    if state.trailing_active:
        if is_long:
            new_stop = state.high_water * (Decimal("1") - trailing_stop_pct)
            state.stop_price = max(state.stop_price, new_stop)
        else:
            new_stop = state.low_water * (Decimal("1") + trailing_stop_pct)
            state.stop_price = min(state.stop_price, new_stop)

    # --- 4) SIGNAL EXIT ---
    exit_met = any(
        evaluate_condition(c, row, prev, adx_threshold) for c in signal_exit
    )
    if not is_long:
        inv_exit = [invert_condition(c) for c in signal_exit]
        exit_met = exit_met or any(
            evaluate_condition(c, row, prev, adx_threshold) for c in inv_exit
        )

    if exit_met:
        close_amount = abs(state.position)
        pnl = _compute_pnl(is_long, state.entry_price, price, close_amount, fee_pct)

        state.capital += pnl
        trade = build_trade(
            entry_ts=state.entry_ts,
            exit_ts_raw=row["timestamp"],
            entry_price=state.entry_price,
            exit_price=price,
            close_amount=close_amount,
            pnl=pnl,
            entry_regime=state.entry_regime,
            strategy_name=current_strategy["name"],
            exit_reason="signal_exit",
            is_long=is_long,
            initial_exposure=state.initial_exposure,
            high_water=state.high_water,
            low_water=state.low_water,
            entry_stop_price=state.entry_stop_price,
            fixed_rr=fixed_rr,
            stop_distance_pct=state.entry_stop_distance_pct,
            take_profit_multiple=state.entry_rr_multiple,
        )
        state.trades.append(trade)
        state.regime_pnl[state.entry_regime] += pnl

        state.equity.append(state.capital)
        state.position = Decimal("0")


def close_at_end_of_data(
    state: BacktestState,
    last_row: pd.Series,
    current_strategy,
    fixed_rr: Decimal,
    fee_pct: Decimal,
) -> None:
    if state.position == 0:
        return

    price = Decimal(str(last_row["close"]))
    is_long = state.position > 0
    close_amount = abs(state.position)
    pnl = _compute_pnl(is_long, state.entry_price, price, close_amount, fee_pct)

    state.capital += pnl
    trade = build_trade(
        entry_ts=state.entry_ts,
        exit_ts_raw=last_row["timestamp"],
        entry_price=state.entry_price,
        exit_price=price,
        close_amount=close_amount,
        pnl=pnl,
        entry_regime=state.entry_regime,
        strategy_name=current_strategy["name"],
        exit_reason="end_of_simulation",
        is_long=is_long,
        initial_exposure=state.initial_exposure,
        high_water=state.high_water,
        low_water=state.low_water,
        entry_stop_price=state.entry_stop_price,
        fixed_rr=fixed_rr,
        stop_distance_pct=state.entry_stop_distance_pct,
        take_profit_multiple=state.entry_rr_multiple,
    )
    state.trades.append(trade)
    state.regime_pnl[state.entry_regime] += pnl
    state.equity.append(state.capital)
    state.position = Decimal("0")

# core/exits.py v0.4 (285 lines)
