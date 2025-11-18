# core/sizing.py
# Purpose: Provide mode/risk parameters and position sizing helpers for the backtest engine.
# Major External Functions/Classes: get_mode_params, safe_decimal, compute_position_and_stops
# Notes: Logic mirrors the original sizing behavior from engine v1.7.

from decimal import Decimal
from typing import Tuple


def safe_decimal(value, name: str = "", default: float = 0.0) -> Decimal:
    if value is None:
        return Decimal(str(default))
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(float(value)))
    if isinstance(value, str):
        val = value.strip()
        if val.endswith("%"):
            try:
                return Decimal(val[:-1]) / Decimal("100")
            except Exception:
                return Decimal(str(default))
        try:
            return Decimal(val)
        except Exception:
            return Decimal(str(default))
    return Decimal(str(default))


def get_mode_params(mode: str) -> Tuple[Decimal, float, float]:
    m = mode.lower()
    if m == "conservative":
        return Decimal("0.02"), 4.0, 40.0
    if m == "aggressive":
        return Decimal("0.04"), 4.0, 25.0
    return Decimal("0.01"), 1.5, 30.0


def compute_position_and_stops(
    capital: Decimal,
    price: Decimal,
    position_frac: Decimal,
    risk_per_trade_frac: Decimal,
    fixed_rr: Decimal,
    sizing: str,
    stop_loss_pct_cfg: Decimal,
    take_profit_pct_cfg: Decimal,
    max_exposure_usd: Decimal,
    fee_pct: Decimal,
):
    if sizing == "equity_pct":
        notional = capital * position_frac
        if notional <= 0 or price <= 0:
            position_size = Decimal("0")
        else:
            position_size = notional / price

        if notional > 0:
            raw_stop = (risk_per_trade_frac / position_frac) - fee_pct
            if raw_stop <= Decimal("0"):
                stop_loss_pct = stop_loss_pct_cfg
            else:
                stop_loss_pct = raw_stop
        else:
            stop_loss_pct = stop_loss_pct_cfg

        take_profit_pct = fixed_rr * stop_loss_pct
    else:
        notional = max_exposure_usd
        position_size = notional / price if price > 0 else Decimal("0")
        stop_loss_pct = stop_loss_pct_cfg
        take_profit_pct = fixed_rr * stop_loss_pct

    return position_size, stop_loss_pct, take_profit_pct

# core/sizing.py v0.2 (75 lines)
