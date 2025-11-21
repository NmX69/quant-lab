# core/conditions.py
# Purpose: Implement entry/exit condition evaluation for all supported indicator types.
# API's: invert_condition, evaluate_condition
# Notes: Logic copied from engine v1.7 and extended in Phase F4 with higher-level primitives.

from decimal import Decimal
from typing import Dict

import pandas as pd


D = Decimal


def invert_condition(cond: Dict) -> Dict:
    """Return a new condition dict that represents the logical inverse.

    This is used primarily for dynamic exit construction or when a strategy
    wants to express the opposite of an existing signal (e.g. for stop/flip).
    Not every type has a perfect inverse; in those cases we return a best-effort
    mirror or the original condition unchanged.
    """

    inv = cond.copy()
    t = cond.get("type")

    if t == "rsi":
        if "below" in cond:
            inv["above"] = 100 - cond["below"]
            inv.pop("below", None)
        elif "above" in cond:
            inv["below"] = 100 - cond["above"]
            inv.pop("above", None)
        return inv

    if t in {"macd_cross", "ema_cross", "stochastic_cross"}:
        direction = cond.get("direction")
        if direction in {"up", "down"}:
            inv["direction"] = "down" if direction == "up" else "up"
        return inv

    if t == "price_above_ema":
        inv["type"] = "price_below_ema"
        return inv

    if t == "price_below_ema":
        inv["type"] = "price_above_ema"
        return inv

    if t == "price_above_bb":
        inv["type"] = "price_below_bb"
        return inv

    if t == "price_below_bb":
        inv["type"] = "price_above_bb"
        return inv

    if t == "price_crosses_mid_bb":
        inv["type"] = "price_crosses_mid_bb_down"
        return inv

    if t == "price_crosses_mid_bb_down":
        inv["type"] = "price_crosses_mid_bb"
        return inv

    if t == "price_near_bb_lower":
        inv["type"] = "price_near_bb_upper"
        return inv

    if t == "price_near_bb_upper":
        inv["type"] = "price_near_bb_lower"
        return inv

    if t == "breakout_high":
        inv["type"] = "breakout_low"
        return inv

    if t == "breakout_low":
        inv["type"] = "breakout_high"
        return inv

    if t == "volatility_expansion":
        inv["type"] = "range_contraction"
        return inv

    if t == "range_contraction":
        inv["type"] = "volatility_expansion"
        return inv

    if t == "trend_pullback":
        direction = cond.get("direction")
        if direction in {"long", "short"}:
            inv["direction"] = "short" if direction == "long" else "long"
        return inv

    return inv


def evaluate_condition(cond: Dict, row: pd.Series, prev: pd.Series, adx_threshold: float) -> bool:
    """Evaluate a single condition against the current and previous bar.

    Args:
        cond: Condition dictionary from SDL.
        row: Current candle (pandas Series with indicator columns).
        prev: Previous candle (same structure as row).
        adx_threshold: Default ADX threshold for conditions that choose
            "mode_threshold" instead of a numeric value.
    """

    t = cond.get("type")

    # --- MACD crossover ---
    if t == "macd_cross":
        direction = cond.get("direction", "up")
        if direction == "up":
            return prev["macd"] <= prev["signal"] and row["macd"] > row["signal"]
        return prev["macd"] >= prev["signal"] and row["macd"] < row["signal"]

    # --- EMA crossover ---
    if t == "ema_cross":
        fast_p = cond.get("fast", 50)
        slow_p = cond.get("slow", 150)
        fast_col = f"ema_{fast_p}"
        slow_col = f"ema_{slow_p}"
        if fast_col not in row or slow_col not in row:
            return False
        direction = cond.get("direction", "up")
        if direction == "up":
            return prev[fast_col] <= prev[slow_col] and row[fast_col] > row[slow_col]
        return prev[fast_col] >= prev[slow_col] and row[fast_col] < row[slow_col]

    # --- Stochastic crossover ---
    if t == "stochastic_cross":
        k_col = "stoch_k"
        d_col = "stoch_d"
        if k_col not in row or d_col not in row:
            return False
        direction = cond.get("direction", "up")
        if direction == "up":
            return prev[k_col] <= prev[d_col] and row[k_col] > row[d_col]
        return prev[k_col] >= prev[d_col] and row[k_col] < row[d_col]

    # --- ADX threshold ---
    if t == "adx":
        thresh = cond.get("above", adx_threshold)
        if thresh == "mode_threshold":
            thresh = adx_threshold
        if "below" in cond:
            return float(row["adx"]) < float(cond["below"])
        return float(row["adx"]) > float(thresh)

    # --- Price vs EMA ---
    if t == "price_above_ema":
        p = cond.get("period", 150)
        col = f"ema_{p}"
        if col not in row:
            return False
        return D(str(row["close"])) > D(str(row[col]))

    if t == "price_below_ema":
        p = cond.get("period", 150)
        col = f"ema_{p}"
        if col not in row:
            return False
        return D(str(row["close"])) < D(str(row[col]))

    # --- RSI ---
    if t == "rsi":
        if "below" in cond:
            return float(row["rsi"]) < float(cond["below"])
        if "above" in cond:
            return float(row["rsi"]) > float(cond["above"])
        return False

    # --- Volume z-score ---
    if t == "volume_zscore":
        if "volume_zscore" not in row:
            return False
        z = float(row["volume_zscore"])
        if "below" in cond:
            return z < float(cond["below"])
        threshold = float(cond.get("above", cond.get("min", 2.0)))
        return z > threshold

    # --- Bollinger-band location ---
    if t == "price_above_bb":
        if "bb_upper" not in row:
            return False
        return D(str(row["close"])) > D(str(row["bb_upper"]))

    if t == "price_below_bb":
        if "bb_lower" not in row:
            return False
        return D(str(row["close"])) < D(str(row["bb_lower"]))

    if t == "price_near_bb_lower":
        if "bb_lower" not in row or "bb_mid" not in row:
            return False
        lower = D(str(row["bb_lower"]))
        mid = D(str(row["bb_mid"]))
        buffer = (mid - lower) * D("0.1")
        price = D(str(row["close"]))
        return price <= lower + buffer

    if t == "price_near_bb_upper":
        if "bb_upper" not in row or "bb_mid" not in row:
            return False
        upper = D(str(row["bb_upper"]))
        mid = D(str(row["bb_mid"]))
        buffer = (upper - mid) * D("0.1")
        price = D(str(row["close"]))
        return price >= upper - buffer

    if t == "price_crosses_mid_bb":
        if "bb_mid" not in row:
            return False
        return prev["close"] < prev["bb_mid"] and row["close"] >= row["bb_mid"]

    if t == "price_crosses_mid_bb_down":
        if "bb_mid" not in row:
            return False
        return prev["close"] > prev["bb_mid"] and row["close"] <= row["bb_mid"]

    # --- Phase F4: higher-level primitives ---

    if t == "breakout_high":
        """Close breaks above the upper Bollinger band by an optional buffer.

        Parameters:
            buffer_pct (float, optional): Extra fraction above the upper band
                required to count as a breakout. Defaults to 0.0.
        """

        if "bb_upper" not in row:
            return False
        price = D(str(row["close"]))
        upper = D(str(row["bb_upper"]))
        buffer_pct = D(str(cond.get("buffer_pct", 0.0)))
        return price > upper * (D("1") + buffer_pct)

    if t == "breakout_low":
        """Close breaks below the lower Bollinger band by an optional buffer."""

        if "bb_lower" not in row:
            return False
        price = D(str(row["close"]))
        lower = D(str(row["bb_lower"]))
        buffer_pct = D(str(cond.get("buffer_pct", 0.0)))
        return price < lower * (D("1") - buffer_pct)

    if t == "volatility_expansion":
        """ATR-based volatility expansion detector.

        Parameters:
            multiplier (float): Current ATR must be greater than
                multiplier * previous ATR. Defaults to 1.5.
        """

        if "atr" not in row or "atr" not in prev or prev["atr"] == 0:
            return False
        curr_atr = D(str(row["atr"]))
        prev_atr = D(str(prev["atr"]))
        ratio = curr_atr / prev_atr if prev_atr != 0 else D("0")
        multiplier = D(str(cond.get("multiplier", 1.5)))
        return ratio > multiplier

    if t == "range_contraction":
        """ATR-based volatility contraction detector (inverse of expansion)."""

        if "atr" not in row or "atr" not in prev or prev["atr"] == 0:
            return False
        curr_atr = D(str(row["atr"]))
        prev_atr = D(str(prev["atr"]))
        ratio = curr_atr / prev_atr if prev_atr != 0 else D("0")
        multiplier = D(str(cond.get("multiplier", 0.75)))
        return ratio < multiplier

    if t == "trend_pullback":
        """Detect a pullback toward an EMA within a bounded percentage window.

        Parameters:
            period (int): EMA period to use (default 50).
            max_pullback_pct (float): Maximum fractional distance from the EMA
                allowed to still count as a pullback (default 0.02 == 2%).
            direction ("long" | "short", optional): If provided, enforces that
                the pullback is in the given trade direction. If omitted, the
                check is symmetric around the EMA.
        """

        period = cond.get("period", 50)
        col = f"ema_{period}"
        if col not in row:
            return False
        price = D(str(row["close"]))
        ema = D(str(row[col]))
        max_pullback_pct = D(str(cond.get("max_pullback_pct", 0.02)))
        direction = cond.get("direction")

        if direction == "long":
            # Price has pulled back below the EMA, but not too far.
            lower_bound = ema * (D("1") - max_pullback_pct)
            return lower_bound <= price <= ema
        if direction == "short":
            # Price has retraced above the EMA, but not too far.
            upper_bound = ema * (D("1") + max_pullback_pct)
            return ema <= price <= upper_bound

        # Symmetric: price within a band around EMA.
        lower_bound = ema * (D("1") - max_pullback_pct)
        upper_bound = ema * (D("1") + max_pullback_pct)
        return lower_bound <= price <= upper_bound

    return False
# core/conditions.py v0.3 (314 lines)
