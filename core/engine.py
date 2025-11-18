# core/engine.py
# Purpose: Orchestrate regime-aware backtests and delegate sizing, conditions, exits, state, and results to helper modules.
# Major External Functions/Classes: run_backtest
# Notes: Refactor pass 2 — main loop delegations; behavior preserved from engine v1.7.

from decimal import Decimal
from typing import Tuple, Dict, Optional

import pandas as pd

from core.strategy_loader import get_strategy
from core.regime_router import get_active_strategy
from core.results import BacktestResult
from core.sizing import (
    get_mode_params,
    safe_decimal,
)
from core.state import (
    BacktestState,
    init_backtest_state,
    update_regime_for_bar,
    update_position_tracking_for_bar,
    maybe_open_position,
)
from core.exits import (
    handle_exits_for_bar,
    close_at_end_of_data,
)
from core.results_builder import build_backtest_result

STARTING_CAPITAL = Decimal("100.0")
FEE_PCT = Decimal("0.001")  # 0.1% round-trip fee model

STRATEGY_TRENDING_UP = "trending_up"
STRATEGY_TRENDING_DOWN = "trending_down"
STRATEGY_RANGING = "ranging"


def _load_initial_strategy(
    df: pd.DataFrame,
    strategy_name: str,
    use_router: bool,
    strategy_mappings: Optional[Dict],
):
    if use_router:
        first_regime = df.iloc[0]["regime"]
        return get_active_strategy(first_regime, strategy_mappings)
    return get_strategy(strategy_name)


def _load_risk_exit_config(strategy: Dict) -> Dict:
    """Extract risk / exit config from a strategy dict (no side effects)."""
    exit_cfg = strategy["exit"]
    risk_cfg = strategy.get("risk", {})

    stop_loss_pct_cfg = safe_decimal(exit_cfg.get("stop_loss", 0.03), "stop_loss", 0.03)
    take_profit_pct_cfg = safe_decimal(exit_cfg.get("take_profit", 0.18), "take_profit", 0.18)
    partial_exit_pct = safe_decimal(exit_cfg.get("partial_exit", 0.0), "partial_exit", 0.0)
    trailing_stop_pct = safe_decimal(exit_cfg.get("trailing_stop", 0.0), "trailing_stop", 0.0)

    sizing = risk_cfg.get("sizing", "equity_pct")
    if sizing == "atr":
        sizing = "equity_pct"
    max_exposure_usd = safe_decimal(risk_cfg.get("max_exposure_usd", 100), "max_exposure_usd", 100)

    return {
        "stop_loss_pct_cfg": stop_loss_pct_cfg,
        "take_profit_pct_cfg": take_profit_pct_cfg,
        "partial_exit_pct": partial_exit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "sizing": sizing,
        "max_exposure_usd": max_exposure_usd,
    }


def run_backtest(
    df: pd.DataFrame,
    mode: str,
    strategy_name: str,
    use_router: bool = False,
    strategy_mappings: Optional[Dict] = None,
    position_pct: float = 15.0,   # % of equity used as position notional
    risk_pct: float = 1.0,        # % of equity risked per trade
    reward_rr: Optional[float] = None,  # reward:risk multiple; None -> use mode default
) -> Tuple[str, BacktestResult]:
    """Main public entrypoint for running a regime-aware backtest."""
    if df.empty:
        return "No data", None

    # --- MODE / RISK PARAMS (unchanged behavior) ---
    mode_risk_frac, mode_rr, adx_threshold = get_mode_params(mode)

    position_frac = Decimal(str(max(position_pct, 0.1) / 100.0))
    if risk_pct is not None:
        risk_per_trade_frac = Decimal(str(max(risk_pct, 0.01) / 100.0))
    else:
        risk_per_trade_frac = mode_risk_frac

    if reward_rr is not None:
        fixed_rr = Decimal(str(max(reward_rr, 0.1)))
    else:
        fixed_rr = Decimal(str(mode_rr))

    # --- INITIAL STRATEGY + CONFIG ---
    current_strategy = _load_initial_strategy(df, strategy_name, use_router, strategy_mappings)
    entry_conditions = current_strategy["entry"]["conditions"]
    signal_exit = current_strategy["exit"].get("signal_exit", [])

    cfg = _load_risk_exit_config(current_strategy)
    stop_loss_pct_cfg = cfg["stop_loss_pct_cfg"]
    take_profit_pct_cfg = cfg["take_profit_pct_cfg"]
    partial_exit_pct = cfg["partial_exit_pct"]
    trailing_stop_pct = cfg["trailing_stop_pct"]
    sizing = cfg["sizing"]
    max_exposure_usd = cfg["max_exposure_usd"]

    # This is the "R" for future trades; per-trade stop % is derived at entry.
    # (Same semantics as before.)
    # stop_loss_pct and take_profit_pct are recomputed on each entry.
    # Here we simply set a baseline consistent with previous code.
    stop_loss_pct = stop_loss_pct_cfg
    take_profit_pct = fixed_rr * stop_loss_pct

    # --- STATE OBJECT ---
    state: BacktestState = init_backtest_state(
        starting_capital=STARTING_CAPITAL,
        regime_up_label=STRATEGY_TRENDING_UP,
        regime_down_label=STRATEGY_TRENDING_DOWN,
        regime_range_label=STRATEGY_RANGING,
    )

    # --- MAIN LOOP ---
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        # REGIME FOR THIS BAR
        current_regime = (
            STRATEGY_TRENDING_UP
            if row["trending_up"]
            else STRATEGY_TRENDING_DOWN
            if row["trending_down"]
            else STRATEGY_RANGING
        )

        update_regime_for_bar(state, current_regime)

        price = Decimal(str(row["close"]))
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))

        # ROUTER UPDATE (if enabled) — same semantics as before
        if use_router:
            current_strategy = get_active_strategy(current_regime, strategy_mappings)
            entry_conditions = current_strategy["entry"]["conditions"]
            signal_exit = current_strategy["exit"].get("signal_exit", [])
            cfg = _load_risk_exit_config(current_strategy)
            stop_loss_pct_cfg = cfg["stop_loss_pct_cfg"]
            take_profit_pct_cfg = cfg["take_profit_pct_cfg"]
            partial_exit_pct = cfg["partial_exit_pct"]
            trailing_stop_pct = cfg["trailing_stop_pct"]
            sizing = cfg["sizing"]
            max_exposure_usd = cfg["max_exposure_usd"]

            stop_loss_pct = stop_loss_pct_cfg
            take_profit_pct = fixed_rr * stop_loss_pct

        # UPDATE HIGH/LOW WATER WHILE IN A POSITION
        update_position_tracking_for_bar(state, high=high, low=low)

        # ENTRY LOGIC (only if flat)
        maybe_open_position(
            state=state,
            row=row,
            prev=prev,
            current_strategy=current_strategy,
            current_regime=current_regime,
            adx_threshold=adx_threshold,
            sizing=sizing,
            position_frac=position_frac,
            risk_per_trade_frac=risk_per_trade_frac,
            fixed_rr=fixed_rr,
            stop_loss_pct_cfg=stop_loss_pct_cfg,
            take_profit_pct_cfg=take_profit_pct_cfg,
            max_exposure_usd=max_exposure_usd,
            trailing_stop_pct=trailing_stop_pct,
            fee_pct=FEE_PCT,
        )

        # EXIT LOGIC (if in a position)
        handle_exits_for_bar(
            state=state,
            row=row,
            prev=prev,
            current_strategy=current_strategy,
            signal_exit=signal_exit,
            trailing_stop_pct=trailing_stop_pct,
            fixed_rr=fixed_rr,
            fee_pct=FEE_PCT,
            adx_threshold=adx_threshold,
            partial_exit_pct=partial_exit_pct,
        )

    # FINAL CLOSE AT END OF DATA (if still in a position)
    close_at_end_of_data(
        state=state,
        last_row=df.iloc[-1],
        current_strategy=current_strategy,
        fixed_rr=fixed_rr,
        fee_pct=FEE_PCT,
    )

    # --- RESULTS / SUMMARY ---
    summary, result = build_backtest_result(
        mode=mode,
        capital=state.capital,
        starting_capital=STARTING_CAPITAL,
        equity=state.equity,
        trades=state.trades,
        regime_changes=state.regime_changes,
        regime_counts=state.regime_counts,
        regime_pnl=state.regime_pnl,
    )
    return summary, result

# core/engine.py v2.1 (226 lines)
