# core/engine.py
# PHASE A 100% — 1% risk per trade, ATR stops from JSON, strict 1.5:1 R:R, canonical fields ready

import pandas as pd
from decimal import Decimal
from typing import List, Tuple, Dict

from core.strategy_loader import get_strategy
from core.regime_router import get_active_strategy
from core.results import BacktestResult, TradeLog
import numpy as np

STARTING_CAPITAL = Decimal("100.0")
FEE_PCT = Decimal("0.001")

STRATEGY_TRENDING_UP = "trending_up"
STRATEGY_TRENDING_DOWN = "trending_down"
STRATEGY_RANGING = "ranging"


def _safe_decimal(value, name: str = "", default: float = 0.0) -> Decimal:
    if value is None:
        return Decimal(str(default))
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(float(value)))  # force through float to handle NaN/inf
    if isinstance(value, str):
        val = value.strip()
        if val.endswith('%'):
            try:
                return Decimal(val[:-1]) / Decimal('100')
            except Exception:
                return Decimal(str(default))
        try:
            return Decimal(val)
        except Exception:
            return Decimal(str(default))
    return Decimal(str(default))


def get_mode_params(mode: str) -> Tuple[Decimal, float, float]:
    """
    Returns:
        risk_per_trade_frac: Decimal, e.g. 0.01 = 1% of equity
        fixed_rr: float, target reward:risk
        adx_threshold: float
    """
    m = mode.lower()
    if m == "conservative":
        return Decimal("0.02"), 4.0, 40.0
    if m == "aggressive":
        return Decimal("0.04"), 4.0, 25.0
    # NORMAL
    return Decimal("0.01"), 1.5, 30.0


def invert_condition(cond: Dict) -> Dict:
    inv = cond.copy()
    t = cond["type"]
    if t == "rsi":
        if "below" in cond:
            inv["above"] = 100 - cond["below"]
            inv.pop("below", None)
        elif "above" in cond:
            inv["below"] = 100 - cond["above"]
            inv.pop("above", None)
    elif t == "macd_cross":
        inv["direction"] = "down" if cond["direction"] == "up" else "up"
    elif t == "ema_cross":
        inv["direction"] = "down" if cond["direction"] == "up" else "up"
    elif t == "stochastic_cross":
        inv["direction"] = "down" if cond["direction"] == "up" else "up"
    elif t == "price_above_ema":
        inv["type"] = "price_below_ema"
    elif t == "price_below_ema":
        inv["type"] = "price_above_ema"
    elif t == "price_above_bb":
        inv["type"] = "price_below_bb"
    elif t == "price_below_bb":
        inv["type"] = "price_above_bb"
    elif t == "price_crosses_mid_bb":
        inv["type"] = "price_crosses_mid_bb_down"
    elif t == "price_crosses_mid_bb_down":
        inv["type"] = "price_crosses_mid_bb"
    elif t == "price_near_bb_lower":
        inv["type"] = "price_near_bb_upper"
    return inv


def evaluate_condition(cond: Dict, row: pd.Series, prev: pd.Series, adx_threshold: float) -> bool:
    t = cond["type"]
    if t == "macd_cross":
        if cond["direction"] == "up":
            return prev["macd"] <= prev["signal"] and row["macd"] > row["signal"]
        return prev["macd"] >= prev["signal"] and row["macd"] < row["signal"]

    if t == "ema_cross":
        fast_p = cond.get("fast", 50)
        slow_p = cond.get("slow", 150)
        fast_col = f"ema_{fast_p}"
        slow_col = f"ema_{slow_p}"
        if fast_col not in row or slow_col not in row:
            return False
        if cond["direction"] == "up":
            return prev[fast_col] <= prev[slow_col] and row[fast_col] > row[slow_col]
        return prev[fast_col] >= prev[slow_col] and row[fast_col] < row[slow_col]

    if t == "stochastic_cross":
        if "below" in cond and row["stoch_k"] >= cond["below"]:
            return False
        if "above" in cond and row["stoch_k"] <= cond["above"]:
            return False
        if cond["direction"] == "up":
            return prev["stoch_k"] <= prev["stoch_d"] and row["stoch_k"] > row["stoch_d"]
        return prev["stoch_k"] >= prev["stoch_d"] and row["stoch_k"] < row["stoch_d"]

    if t == "adx":
        thresh = cond.get("above", adx_threshold)
        if thresh == "mode_threshold":
            thresh = adx_threshold
        if "below" in cond:
            return row["adx"] < float(cond["below"])
        return row["adx"] > float(thresh)

    if t == "price_above_ema":
        p = cond.get("period", 150)
        col = f"ema_{p}"
        if col not in row:
            return False
        return Decimal(str(row["close"])) > Decimal(str(row[col]))

    if t == "price_below_ema":
        p = cond.get("period", 150)
        col = f"ema_{p}"
        if col not in row:
            return False
        return Decimal(str(row["close"])) < Decimal(str(row[col]))

    if t == "rsi":
        if "below" in cond:
            return row["rsi"] < cond["below"]
        if "above" in cond:
            return row["rsi"] > cond["above"]
        return False

    if t == "price_below_bb":
        return Decimal(str(row["close"])) < Decimal(str(row["bb_lower"]))

    if t == "price_above_bb":
        return Decimal(str(row["close"])) > Decimal(str(row["bb_upper"]))

    if t == "price_near_bb_lower":
        buffer = Decimal(str(row["bb_mid"] - row["bb_lower"])) * Decimal("0.1")
        return Decimal(str(row["close"])) <= Decimal(str(row["bb_lower"])) + buffer

    if t == "price_near_bb_upper":
        buffer = Decimal(str(row["bb_upper"] - row["bb_mid"])) * Decimal("0.1")
        return Decimal(str(row["close"])) >= Decimal(str(row["bb_upper"])) - buffer

    if t == "price_crosses_mid_bb":
        return prev["close"] < prev["bb_mid"] and row["close"] >= row["bb_mid"]

    if t == "price_crosses_mid_bb_down":
        return prev["close"] > prev["bb_mid"] and row["close"] <= row["bb_mid"]

    return False


def _build_trade(
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
    # MAE / MFE in % relative to entry
    if is_long:
        mae = ((low_water - entry_price) / entry_price * 100) if entry_price != 0 else Decimal("0")
        mfe = ((high_water - entry_price) / entry_price * 100) if entry_price != 0 else Decimal("0")
    else:
        mae = ((entry_price - high_water) / entry_price * 100) if entry_price != 0 else Decimal("0")
        mfe = ((entry_price - low_water) / entry_price * 100) if entry_price != 0 else Decimal("0")

    pnl_pct = (pnl / initial_exposure) * 100 if initial_exposure else Decimal("0")

    # Hold time in hours
    try:
        entry_dt = pd.to_datetime(entry_ts)
        exit_dt = pd.to_datetime(exit_ts_raw)
        hold_time_hours = (exit_dt - entry_dt).total_seconds() / 3600.0
    except Exception:
        hold_time_hours = 0.0

    # R multiple (pnl divided by risk)
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


def run_backtest(
    df: pd.DataFrame,
    mode: str,
    strategy_name: str,
    use_router: bool = False,
    strategy_mappings: Dict = None
) -> Tuple[str, BacktestResult]:
    if df.empty:
        return "No data", None

    # --- SETUP ---
    risk_per_trade_frac, fixed_rr_float, adx_threshold = get_mode_params(mode)
    fixed_rr = Decimal(str(fixed_rr_float))

    current_strategy = (
        get_active_strategy(df.iloc[0]["regime"], strategy_mappings)
        if use_router
        else get_strategy(strategy_name)
    )

    entry_conditions = current_strategy["entry"]["conditions"]
    signal_exit = current_strategy["exit"].get("signal_exit", [])

    # Base exit parameters from strategy JSON (we’ll enforce 1.5R on top)
    stop_loss_pct_cfg = _safe_decimal(current_strategy["exit"].get("stop_loss", 0.03), "stop_loss", 0.03)
    take_profit_pct_cfg = _safe_decimal(current_strategy["exit"].get("take_profit", 0.18), "take_profit", 0.18)
    partial_exit_pct = _safe_decimal(current_strategy["exit"].get("partial_exit", 0.0), "partial_exit", 0.0)
    trailing_stop_pct = _safe_decimal(current_strategy["exit"].get("trailing_stop", 0.0), "trailing_stop", 0.0)

    sizing = current_strategy["risk"]["sizing"]
    max_exposure_usd = _safe_decimal(current_strategy["risk"].get("max_exposure_usd", 100), "max_exposure_usd", 100)
    atr_multiplier = _safe_decimal(current_strategy["risk"].get("atr_multiplier", 1.0), "atr_multiplier", 1.0)

    # Working copies used per-trade
    stop_loss_pct = stop_loss_pct_cfg
    take_profit_pct = fixed_rr * stop_loss_pct  # strict R:R enforcement as baseline

    capital = STARTING_CAPITAL
    position = Decimal("0")
    entry_price = Decimal("0")
    entry_ts = ""
    entry_regime = ""
    initial_exposure = Decimal("0")
    stop_price = Decimal("0")
    high_water = Decimal("0")
    low_water = Decimal("0")
    trailing_active = False

    # Canonical per-trade fields
    entry_stop_price = Decimal("0")
    entry_stop_distance_pct = 0.0
    entry_rr_multiple = float(fixed_rr)

    trades: List[TradeLog] = []
    equity = [capital]
    regime_pnl = {
        STRATEGY_TRENDING_UP: Decimal("0"),
        STRATEGY_TRENDING_DOWN: Decimal("0"),
        STRATEGY_RANGING: Decimal("0"),
    }
    regime_changes = 0
    prev_regime = None
    trending_up_count = trending_down_count = ranging_count = 0

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        # --- REGIME TRACKING ---
        current_regime = (
            STRATEGY_TRENDING_UP
            if row["trending_up"]
            else STRATEGY_TRENDING_DOWN
            if row["trending_down"]
            else STRATEGY_RANGING
        )

        if current_regime != prev_regime:
            if prev_regime is not None:
                regime_changes += 1
            prev_regime = current_regime

        if current_regime == STRATEGY_TRENDING_UP:
            trending_up_count += 1
        elif current_regime == STRATEGY_TRENDING_DOWN:
            trending_down_count += 1
        else:
            ranging_count += 1

        price = Decimal(str(row["close"]))
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))

        # --- ROUTER UPDATE ---
        if use_router:
            current_strategy = get_active_strategy(current_regime, strategy_mappings)
            entry_conditions = current_strategy["entry"]["conditions"]
            signal_exit = current_strategy["exit"].get("signal_exit", [])

            # Reload base risk/exit config from JSON
            stop_loss_pct_cfg = _safe_decimal(current_strategy["exit"].get("stop_loss", 0.03), "stop_loss", 0.03)
            take_profit_pct_cfg = _safe_decimal(
                current_strategy["exit"].get("take_profit", 0.18), "take_profit", 0.18
            )
            partial_exit_pct = _safe_decimal(
                current_strategy["exit"].get("partial_exit", 0.0), "partial_exit", 0.0
            )
            trailing_stop_pct = _safe_decimal(
                current_strategy["exit"].get("trailing_stop", 0.0), "trailing_stop", 0.0
            )
            sizing = current_strategy["risk"]["sizing"]
            max_exposure_usd = _safe_decimal(
                current_strategy["risk"].get("max_exposure_usd", 100), "max_exposure_usd", 100
            )
            atr_multiplier = _safe_decimal(
                current_strategy["risk"].get("atr_multiplier", 1.0), "atr_multiplier", 1.0
            )

            # Enforce baseline R:R on *future* trades
            stop_loss_pct = stop_loss_pct_cfg
            take_profit_pct = fixed_rr * stop_loss_pct

        # --- POSITION TRACKING ---
        is_long = position > 0
        if position != 0:
            if is_long:
                high_water = max(high_water, high)
                low_water = min(low_water, low)
            else:
                high_water = min(high_water, high)
                low_water = max(low_water, low)

        # --- ENTRY ---
        if position == 0:
            entry_met = all(evaluate_condition(c, row, prev, adx_threshold) for c in entry_conditions)

            # Allow mirrored conditions for shorts
            if current_strategy["direction"] in ["short", "both"]:
                short_entry = all(
                    evaluate_condition(invert_condition(c), row, prev, adx_threshold)
                    for c in entry_conditions
                )
                if current_strategy["direction"] == "short":
                    entry_met = short_entry
                elif current_strategy["direction"] == "both":
                    entry_met = entry_met or short_entry

            if entry_met:
                direction = current_strategy["direction"]
                # In "both", we treat signal as long by default (you can add explicit short logic later)
                is_long = direction in ["long", "both"]

                # --- POSITION SIZING WITH FULL SAFETY ---
                if sizing == "atr":
                    # 1–4% risk of equity depending on mode
                    risk_amount = capital * risk_per_trade_frac

                    atr_val = Decimal(str(row["atr"])) if not pd.isna(row["atr"]) else Decimal("0")
                    stop_distance = atr_val * atr_multiplier

                    # Force minimum stop distance (0.5% of price)
                    min_stop = price * Decimal("0.005")
                    if stop_distance <= 0:
                        stop_distance = min_stop
                    else:
                        stop_distance = max(stop_distance, min_stop)

                    position_size = risk_amount / stop_distance
                    # print(f"ATR ENTRY: price={price}, atr={atr_val}, stop_distance={stop_distance}, position_size={position_size}")

                    # Derive stop % from ATR for this trade
                    stop_loss_pct = stop_distance / price
                    take_profit_pct = fixed_rr * stop_loss_pct  # strict 1.5R (or mode R) from JSON ATR

                elif sizing == "equity_pct":
                    # Risk a fixed fraction of equity in notional terms; stop is still percentage based
                    notional = capital * risk_per_trade_frac
                    position_size = notional / price
                    stop_loss_pct = stop_loss_pct_cfg
                    take_profit_pct = fixed_rr * stop_loss_pct
                else:
                    # fixed_usd sizing
                    position_size = max_exposure_usd / price
                    stop_loss_pct = stop_loss_pct_cfg
                    take_profit_pct = fixed_rr * stop_loss_pct

                # Final guard
                if position_size <= 0 or not position_size.is_finite():
                    position_size = Decimal("0.001")

                position = position_size if is_long else -position_size
                entry_price = price
                entry_ts = str(row["timestamp"])
                entry_regime = current_regime
                initial_exposure = abs(position) * price

                # Stop and canonical fields
                stop_price = (
                    entry_price * (Decimal("1") - stop_loss_pct)
                    if is_long
                    else entry_price * (Decimal("1") + stop_loss_pct)
                )
                high_water = entry_price
                low_water = entry_price
                trailing_active = trailing_stop_pct > 0

                entry_stop_price = stop_price
                entry_stop_distance_pct = float(
                    (abs(entry_price - stop_price) / entry_price) * 100
                ) if entry_price != 0 else 0.0
                entry_rr_multiple = float(
                    (take_profit_pct / stop_loss_pct) if stop_loss_pct != 0 else fixed_rr
                )

                equity.append(capital)
                # print(f"ENTRY: {entry_ts} | {'LONG' if is_long else 'SHORT'} | size={position} | price={price}")

        # --- EXIT LOGIC ---
        if position != 0:
            is_long = position > 0

            # Take-profit level based on this trade's enforced R:R
            tp_price = (
                entry_price * (Decimal("1") + take_profit_pct)
                if is_long
                else entry_price * (Decimal("1") - take_profit_pct)
            )

            # 1) TAKE PROFIT
            if (is_long and price >= tp_price) or (not is_long and price <= tp_price):
                close_amount = abs(position) * (partial_exit_pct if partial_exit_pct > 0 else Decimal("1"))
                fee = FEE_PCT * (close_amount * price)
                if is_long:
                    pnl = (price - entry_price) * close_amount - fee
                else:
                    pnl = (entry_price - price) * close_amount - fee

                capital += pnl
                trade = _build_trade(
                    entry_ts=entry_ts,
                    exit_ts_raw=row["timestamp"],
                    entry_price=entry_price,
                    exit_price=price,
                    close_amount=close_amount,
                    pnl=pnl,
                    entry_regime=entry_regime,
                    strategy_name=current_strategy["name"],
                    exit_reason="take_profit",
                    is_long=is_long,
                    initial_exposure=initial_exposure,
                    high_water=high_water,
                    low_water=low_water,
                    entry_stop_price=entry_stop_price,
                    fixed_rr=fixed_rr,
                    stop_distance_pct=entry_stop_distance_pct,
                    take_profit_multiple=entry_rr_multiple,
                )
                trades.append(trade)
                regime_pnl[entry_regime] += pnl

                position -= close_amount if is_long else -close_amount
                equity.append(capital)
                if position == 0:
                    continue  # no further exit checks this bar

            # 2) STOP LOSS (including trailing)
            if (is_long and price <= stop_price) or (not is_long and price >= stop_price):
                close_amount = abs(position)
                fee = FEE_PCT * (close_amount * price)
                if is_long:
                    pnl = (price - entry_price) * close_amount - fee
                else:
                    pnl = (entry_price - price) * close_amount - fee

                capital += pnl
                trade = _build_trade(
                    entry_ts=entry_ts,
                    exit_ts_raw=row["timestamp"],
                    entry_price=entry_price,
                    exit_price=price,
                    close_amount=close_amount,
                    pnl=pnl,
                    entry_regime=entry_regime,
                    strategy_name=current_strategy["name"],
                    exit_reason="stop_loss",
                    is_long=is_long,
                    initial_exposure=initial_exposure,
                    high_water=high_water,
                    low_water=low_water,
                    entry_stop_price=entry_stop_price,
                    fixed_rr=fixed_rr,
                    stop_distance_pct=entry_stop_distance_pct,
                    take_profit_multiple=entry_rr_multiple,
                )
                trades.append(trade)
                regime_pnl[entry_regime] += pnl

                equity.append(capital)
                position = Decimal("0")
                continue

            # 3) TRAILING STOP ADJUSTMENT
            if trailing_active:
                if is_long:
                    new_stop = high_water * (Decimal("1") - trailing_stop_pct)
                    stop_price = max(stop_price, new_stop)
                else:
                    new_stop = low_water * (Decimal("1") + trailing_stop_pct)
                    stop_price = min(stop_price, new_stop)

            # 4) SIGNAL EXIT
            exit_met = any(evaluate_condition(c, row, prev, adx_threshold) for c in signal_exit)
            if not is_long:
                inv_exit = [invert_condition(c) for c in signal_exit]
                exit_met = exit_met or any(
                    evaluate_condition(c, row, prev, adx_threshold) for c in inv_exit
                )

            if exit_met:
                close_amount = abs(position)
                fee = FEE_PCT * (close_amount * price)
                if is_long:
                    pnl = (price - entry_price) * close_amount - fee
                else:
                    pnl = (entry_price - price) * close_amount - fee

                capital += pnl
                trade = _build_trade(
                    entry_ts=entry_ts,
                    exit_ts_raw=row["timestamp"],
                    entry_price=entry_price,
                    exit_price=price,
                    close_amount=close_amount,
                    pnl=pnl,
                    entry_regime=entry_regime,
                    strategy_name=current_strategy["name"],
                    exit_reason="signal_exit",
                    is_long=is_long,
                    initial_exposure=initial_exposure,
                    high_water=high_water,
                    low_water=low_water,
                    entry_stop_price=entry_stop_price,
                    fixed_rr=fixed_rr,
                    stop_distance_pct=entry_stop_distance_pct,
                    take_profit_multiple=entry_rr_multiple,
                )
                trades.append(trade)
                regime_pnl[entry_regime] += pnl

                equity.append(capital)
                position = Decimal("0")

    # --- FINAL CLOSE AT END OF DATA ---
    if position != 0:
        price = Decimal(str(df["close"].iloc[-1]))
        is_long = position > 0
        close_amount = abs(position)
        fee = FEE_PCT * (close_amount * price)
        if is_long:
            pnl = (price - entry_price) * close_amount - fee
        else:
            pnl = (entry_price - price) * close_amount - fee

        capital += pnl
        trade = _build_trade(
            entry_ts=entry_ts,
            exit_ts_raw=df.iloc[-1]["timestamp"],
            entry_price=entry_price,
            exit_price=price,
            close_amount=close_amount,
            pnl=pnl,
            entry_regime=entry_regime,
            strategy_name=current_strategy["name"],
            exit_reason="end_of_simulation",
            is_long=is_long,
            initial_exposure=initial_exposure,
            high_water=high_water,
            low_water=low_water,
            entry_stop_price=entry_stop_price,
            fixed_rr=fixed_rr,
            stop_distance_pct=entry_stop_distance_pct,
            take_profit_multiple=entry_rr_multiple,
        )
        trades.append(trade)
        regime_pnl[entry_regime] += pnl
        equity.append(capital)

    # --- CALCULATE WINRATE & SHARPE ---
    wins = sum(1 for t in trades if t.pnl > 0)
    winrate = (wins / len(trades) * 100) if trades else 0.0

    equity_floats = [float(x) for x in equity]
    if len(equity_floats) > 1:
        returns = np.diff(equity_floats) / np.array(equity_floats[:-1])
        std = np.std(returns)
        sharpe_ratio = (np.mean(returns) / std * np.sqrt(365 * 24)) if std > 0 else 0.0
    else:
        sharpe_ratio = 0.0

    peak = max(equity_floats) if equity_floats else 0.0
    trough = min(equity_floats) if equity_floats else 0.0
    max_dd = peak - trough if equity_floats else 0.0
    max_dd_pct = (max_dd / peak) * 100 if peak > 0 else 0.0

    result = BacktestResult(
        asset="unknown",
        mode=mode,
        final_equity=capital,
        total_return_pct=(capital / STARTING_CAPITAL - 1) * 100,
        total_trades=len(trades),
        winrate=round(winrate, 1),
        sharpe=round(sharpe_ratio, 2),
        max_dd=Decimal(str(max_dd)),
        max_dd_pct=Decimal(str(max_dd_pct)),
        regime_changes=regime_changes,
        regime_counts={
            STRATEGY_TRENDING_UP: trending_up_count,
            STRATEGY_TRENDING_DOWN: trending_down_count,
            STRATEGY_RANGING: ranging_count,
        },
        regime_pnl=regime_pnl,
        equity_curve=equity,
        trades=trades,  # already TradeLog objects
    )

    return result.summary_str() + "\n", result

# core/engine.py v1.5
