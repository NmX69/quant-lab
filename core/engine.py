# core/engine.py
# PHASE 6: NEW CONDITIONS (EMA/STOCH CROSS, NEAR BB), ATR SIZING/STOPS, RISK UPGRADES

import pandas as pd
from decimal import Decimal
from typing import List, Tuple, Dict, NamedTuple

from core.strategy_loader import get_strategy
from core.regime_router import get_active_strategy
from core.results import BacktestResult, TradeLog

STARTING_CAPITAL = Decimal("100.0")
FEE_PCT = Decimal("0.001")

STRATEGY_TRENDING_UP = "trending_up"
STRATEGY_TRENDING_DOWN = "trending_down"
STRATEGY_RANGING = "ranging"


class Trade(NamedTuple):
    entry_ts: str
    exit_ts: str
    entry_price: Decimal
    exit_price: Decimal
    position: Decimal
    pnl: Decimal
    pnl_pct: Decimal
    regime: str
    strategy: str
    exit_reason: str
    mae: Decimal
    mfe: Decimal


def get_mode_params(mode: str) -> Tuple[Decimal, Decimal, float]:
    m = mode.lower()
    if m == "conservative": return Decimal("0.02"), Decimal("4.0"), 40.0
    if m == "aggressive": return Decimal("0.04"), Decimal("4.0"), 25.0
    return Decimal("0.01"), Decimal("1.5"), 30.0


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
        if fast_col not in row or slow_col not in row: return False
        if cond["direction"] == "up":
            return prev[fast_col] <= prev[slow_col] and row[fast_col] > row[slow_col]
        return prev[fast_col] >= prev[slow_col] and row[fast_col] < row[slow_col]
    if t == "stochastic_cross":
        if "below" in cond and row["stoch_k"] >= cond["below"]: return False
        if "above" in cond and row["stoch_k"] <= cond["above"]: return False
        if cond["direction"] == "up":
            return prev["stoch_k"] <= prev["stoch_d"] and row["stoch_k"] > row["stoch_d"]
        return prev["stoch_k"] >= prev["stoch_d"] and row["stoch_k"] < row["stoch_d"]
    if t == "adx":
        thresh = cond.get("above", adx_threshold)
        if thresh == "mode_threshold": thresh = adx_threshold
        if "below" in cond:
            return row["adx"] < float(cond["below"])
        return row["adx"] > float(thresh)
    if t == "price_above_ema":
        p = cond.get("period", 150)
        col = f"ema_{p}"
        if col not in row: return False
        return Decimal(str(row["close"])) > Decimal(str(row[col]))
    if t == "price_below_ema":
        p = cond.get("period", 150)
        col = f"ema_{p}"
        if col not in row: return False
        return Decimal(str(row["close"])) < Decimal(str(row[col]))
    if t == "rsi":
        if "below" in cond: return row["rsi"] < cond["below"]
        if "above" in cond: return row["rsi"] > cond["above"]
        return False
    if t == "price_below_bb":
        return Decimal(str(row["close"])) < Decimal(str(row["bb_lower"]))
    if t == "price_above_bb":
        return Decimal(str(row["close"])) > Decimal(str(row["bb_upper"]))
    if t == "price_near_bb_lower":
        buffer = Decimal(str(row["bb_mid"] - row["bb_lower"])) * Decimal("0.1")  # 10% of band width
        return Decimal(str(row["close"])) <= Decimal(str(row["bb_lower"])) + buffer
    if t == "price_near_bb_upper":
        buffer = Decimal(str(row["bb_upper"] - row["bb_mid"])) * Decimal("0.1")
        return Decimal(str(row["close"])) >= Decimal(str(row["bb_upper"])) - buffer
    if t == "price_crosses_mid_bb":
        return prev["close"] < prev["bb_mid"] and row["close"] >= row["bb_mid"]
    if t == "price_crosses_mid_bb_down":
        return prev["close"] > prev["bb_mid"] and row["close"] <= row["bb_mid"]
    if t == "volume_zscore":
        if "above" in cond: return row["volume_zscore"] > cond["above"]
        if "below" in cond: return row["volume_zscore"] < cond["below"]
        return False
    return False


def run_backtest(df: pd.DataFrame, mode: str, strategy_name: str,
                 use_router: bool = False,
                 strategy_mappings: Dict[str, str] = None) -> Tuple[str, BacktestResult]:
    if df.empty:
        return "No data.\n", BacktestResult(asset="unknown", mode=mode, final_equity=STARTING_CAPITAL,
                                           total_return_pct=Decimal("0"), total_trades=0,
                                           max_dd=Decimal("0"), max_dd_pct=Decimal("0"),
                                           regime_changes=0, regime_counts={}, regime_pnl={},
                                           equity_curve=[], trades=[])

    stop_pct, risk_reward, adx_threshold = get_mode_params(mode)
    capital = STARTING_CAPITAL
    position = Decimal("0")
    entry_price = Decimal("0")
    entry_ts = ""
    entry_regime = ""
    partial_taken = False
    trailing_active = False
    high_water = Decimal("0")
    low_water = Decimal("0")
    initial_exposure = Decimal("0")
    stop_price = Decimal("0")
    tp_price = Decimal("0")
    partial_fraction = Decimal("0")
    signal_exit = []

    trades: List[Trade] = []
    equity: List[Decimal] = [STARTING_CAPITAL]
    regime_pnl: Dict[str, Decimal] = {
        STRATEGY_TRENDING_UP: Decimal("0"),
        STRATEGY_TRENDING_DOWN: Decimal("0"),
        STRATEGY_RANGING: Decimal("0")
    }
    trending_up_count = trending_down_count = ranging_count = 0
    regime_changes = 0
    prev_regime = None

    strategy = get_strategy(strategy_name)
    current_strategy = strategy

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        price = Decimal(str(row["close"]))
        regime = STRATEGY_TRENDING_UP if row["trending_up"] else (
            STRATEGY_TRENDING_DOWN if row["trending_down"] else STRATEGY_RANGING
        )

        # Track regime stats
        if regime != prev_regime:
            regime_changes += 1
            prev_regime = regime
        if regime == STRATEGY_TRENDING_UP:
            trending_up_count += 1
        elif regime == STRATEGY_TRENDING_DOWN:
            trending_down_count += 1
        else:
            ranging_count += 1

        if use_router:
            current_strategy = get_active_strategy(regime, strategy_mappings)

        # Check if regime matches strategy
        if current_strategy["regime"] not in [regime, "both"]:
            continue

        is_long_only = current_strategy["direction"] == "long"
        is_short_only = current_strategy["direction"] == "short"
        is_both = current_strategy["direction"] == "both"

        # Entry logic
        if position == 0:
            entry_conds = current_strategy["entry"]["conditions"]
            entry_met = all(evaluate_condition(c, row, prev, adx_threshold) for c in entry_conds)

            if entry_met and (is_long_only or is_both):
                is_long_entry = True
            elif is_short_only or is_both:
                # Check inverted for short
                inv_conds = [invert_condition(c) for c in entry_conds]
                entry_met = all(evaluate_condition(c, row, prev, adx_threshold) for c in inv_conds)
                is_long_entry = False
            else:
                continue

            if entry_met:
                entry_price = price
                risk_pct = Decimal(str(current_strategy["risk"].get("risk_per_trade_pct", 1.0))) / Decimal("100")
                sizing = current_strategy["risk"]["sizing"]

                if sizing == "equity_pct":
                    risk_amount = capital * risk_pct
                elif sizing == "fixed_usd":
                    risk_amount = Decimal(str(current_strategy["risk"].get("max_exposure_usd", 15.0)))
                elif sizing == "atr":
                    atr = Decimal(str(row["atr"]))
                    multiplier = Decimal(str(current_strategy["risk"].get("atr_multiplier", 2.0)))
                    risk_amount = capital * risk_pct
                    stop_distance = atr * multiplier
                    position_size = risk_amount / stop_distance
                else:
                    risk_amount = Decimal("15.0")  # Fallback

                stop_loss = current_strategy["exit"]["stop_loss"]
                if stop_loss == "mode_stop":
                    stop_pct_used = stop_pct
                elif stop_loss == "atr":
                    atr = Decimal(str(row["atr"]))
                    multiplier = Decimal(str(current_strategy["exit"].get("atr_multiplier_stop", 1.5)))
                    stop_pct_used = (atr * multiplier) / entry_price
                else:
                    stop_pct_used = Decimal(str(stop_loss))

                if sizing != "atr":  # For non-ATR sizing, use stop_distance from stop_pct
                    stop_distance = entry_price * stop_pct_used

                position_size = risk_amount / stop_distance

                # Cap exposure
                max_exposure_pct = Decimal(str(current_strategy["risk"].get("max_exposure_pct", 5.0))) / Decimal("100")
                max_position = (capital * max_exposure_pct) / entry_price
                position_size = min(position_size, max_position)

                position = position_size if is_long_entry else -position_size
                initial_exposure = position_size * entry_price

                entry_ts = str(row["timestamp"])
                entry_regime = regime
                partial_taken = False
                trailing_active = False
                high_water = entry_price
                low_water = entry_price

                take_profit = current_strategy["exit"]["take_profit"]
                tp_distance = risk_reward * stop_pct_used if take_profit == "mode_tp" else Decimal(str(take_profit))

                stop_price = entry_price * (Decimal("1") - stop_pct_used) if is_long_entry else entry_price * (Decimal("1") + stop_pct_used)
                tp_price = entry_price * (Decimal("1") + tp_distance) if is_long_entry else entry_price * (Decimal("1") - tp_distance)
                partial_fraction = Decimal(str(current_strategy["exit"].get("partial_exit", 0.0)))
                signal_exit = current_strategy["exit"].get("signal_exit", [])

        # Position management
        if position != 0:
            is_long = position > 0
            high_water = max(high_water, price) if is_long else high_water
            low_water = min(low_water, price) if not is_long else low_water

            # Check stop loss
            if (is_long and price <= stop_price) or (not is_long and price >= stop_price):
                close_amount = abs(position)
                fee = FEE_PCT * (close_amount * price)
                pnl = (price - entry_price) * close_amount - fee if is_long else (entry_price - price) * close_amount - fee
                capital += pnl
                regime_pnl[entry_regime] += pnl

                mae = Decimal(str(((low_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - high_water) / entry_price) * 100))
                mfe = Decimal(str(((high_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - low_water) / entry_price) * 100))
                pnl_pct = (pnl / initial_exposure) * 100 if initial_exposure else Decimal("0")
                trades.append(Trade(
                    entry_ts=entry_ts,
                    exit_ts=str(row["timestamp"]),
                    entry_price=entry_price,
                    exit_price=price,
                    position=close_amount if is_long else -close_amount,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    regime=entry_regime,
                    strategy=current_strategy["name"],
                    exit_reason="stop_loss",
                    mae=mae,
                    mfe=mfe
                ))
                equity.append(capital)
                position = Decimal("0")
                continue

            # Check take profit or partial
            if (is_long and price >= tp_price) or (not is_long and price <= tp_price):
                if partial_fraction > 0 and not partial_taken:
                    close_amount = abs(position) * partial_fraction
                    fee = FEE_PCT * (close_amount * price)
                    pnl = (price - entry_price) * close_amount - fee if is_long else (entry_price - price) * close_amount - fee
                    capital += pnl
                    regime_pnl[entry_regime] += pnl

                    mae = Decimal(str(((low_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - high_water) / entry_price) * 100))
                    mfe = Decimal(str(((high_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - low_water) / entry_price) * 100))
                    pnl_pct = (pnl / (initial_exposure * partial_fraction)) * 100 if initial_exposure else Decimal("0")
                    trades.append(Trade(
                        entry_ts=entry_ts,
                        exit_ts=str(row["timestamp"]),
                        entry_price=entry_price,
                        exit_price=price,
                        position=close_amount if is_long else -close_amount,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        regime=entry_regime,
                        strategy=current_strategy["name"],
                        exit_reason="partial_take_profit",
                        mae=mae,
                        mfe=mfe
                    ))
                    position -= close_amount if is_long else -close_amount
                    partial_taken = True
                    trailing_active = True  # Activate trailing after partial
                    equity.append(capital)
                else:
                    close_amount = abs(position)
                    fee = FEE_PCT * (close_amount * price)
                    pnl = (price - entry_price) * close_amount - fee if is_long else (entry_price - price) * close_amount - fee
                    capital += pnl
                    regime_pnl[entry_regime] += pnl

                    mae = Decimal(str(((low_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - high_water) / entry_price) * 100))
                    mfe = Decimal(str(((high_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - low_water) / entry_price) * 100))
                    pnl_pct = (pnl / initial_exposure) * 100 if initial_exposure else Decimal("0")
                    trades.append(Trade(
                        entry_ts=entry_ts,
                        exit_ts=str(row["timestamp"]),
                        entry_price=entry_price,
                        exit_price=price,
                        position=close_amount if is_long else -close_amount,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        regime=entry_regime,
                        strategy=current_strategy["name"],
                        exit_reason="take_profit",
                        mae=mae,
                        mfe=mfe
                    ))
                    equity.append(capital)
                    position = Decimal("0")
                    continue

            # Trailing stop if active
            if trailing_active:
                trailing_pct = Decimal(str(current_strategy["exit"].get("trailing_stop", 0.01)))
                if is_long:
                    new_stop = high_water * (Decimal("1") - trailing_pct)
                    stop_price = max(stop_price, new_stop)
                else:
                    new_stop = low_water * (Decimal("1") + trailing_pct)
                    stop_price = min(stop_price, new_stop)

            # Signal exit
            exit_met = any(evaluate_condition(c, row, prev, adx_threshold) for c in signal_exit)
            if not is_long:
                inv_exit = [invert_condition(c) for c in signal_exit]
                exit_met = any(evaluate_condition(c, row, prev, adx_threshold) for c in inv_exit)

            if exit_met:
                close_amount = abs(position)
                fee = FEE_PCT * (close_amount * price)
                pnl = (price - entry_price) * close_amount - fee if is_long else (entry_price - price) * close_amount - fee
                capital += pnl
                regime_pnl[entry_regime] += pnl

                mae = Decimal(str(((low_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - high_water) / entry_price) * 100))
                mfe = Decimal(str(((high_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - low_water) / entry_price) * 100))
                pnl_pct = (pnl / initial_exposure) * 100 if initial_exposure else Decimal("0")
                trades.append(Trade(
                    entry_ts=entry_ts,
                    exit_ts=str(row["timestamp"]),
                    entry_price=entry_price,
                    exit_price=price,
                    position=close_amount if is_long else -close_amount,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    regime=entry_regime,
                    strategy=current_strategy["name"],
                    exit_reason="signal_exit",
                    mae=mae,
                    mfe=mfe
                ))
                equity.append(capital)
                position = Decimal("0")

    # Final close if open
    if position != 0:
        price = Decimal(str(df["close"].iloc[-1]))
        is_long = position > 0
        close_amount = abs(position)
        fee = FEE_PCT * (close_amount * price)
        pnl = (price - entry_price) * close_amount - fee if is_long else (entry_price - price) * close_amount - fee
        capital += pnl
        regime_pnl[entry_regime] += pnl

        mae = Decimal(str(((low_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - high_water) / entry_price) * 100))
        mfe = Decimal(str(((high_water - entry_price) / entry_price) * 100 if is_long else ((entry_price - low_water) / entry_price) * 100))
        pnl_pct = (pnl / initial_exposure) * 100 if initial_exposure else Decimal("0")
        trades.append(Trade(
            entry_ts=entry_ts,
            exit_ts=str(df.iloc[-1]["timestamp"]),
            entry_price=entry_price,
            exit_price=price,
            position=close_amount if is_long else -close_amount,
            pnl=pnl,
            pnl_pct=pnl_pct,
            regime=entry_regime,
            strategy=current_strategy["name"],
            exit_reason="end_of_simulation",
            mae=mae,
            mfe=mfe
        ))
        equity.append(capital)

    peak = max(equity)
    max_dd = peak - min(equity) if equity else Decimal("0")
    max_dd_pct = (max_dd / peak) * 100 if peak > 0 else Decimal("0")

    result = BacktestResult(
        asset="unknown",
        mode=mode,
        final_equity=capital,
        total_return_pct=(capital / STARTING_CAPITAL - 1) * 100,
        total_trades=len(trades),
        max_dd=max_dd,
        max_dd_pct=max_dd_pct,
        regime_changes=regime_changes,
        regime_counts={
            STRATEGY_TRENDING_UP: trending_up_count,
            STRATEGY_TRENDING_DOWN: trending_down_count,
            STRATEGY_RANGING: ranging_count
        },
        regime_pnl=regime_pnl,
        equity_curve=equity,
        trades=[TradeLog(*t) for t in trades]
    )

    return result.summary_str() + "\n", result