# core/conditions.py
# Purpose: Implement entry/exit condition evaluation for all supported indicator types.
# Major External Functions/Classes: invert_condition, evaluate_condition
# Notes: Logic copied from engine v1.7; no behavior changes.

from decimal import Decimal
from typing import Dict

import pandas as pd


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

# core/conditions.py v0.2 (123 lines)
