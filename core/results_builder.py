# core/results_builder.py
# Purpose: Compute performance statistics and build BacktestResult + summary string.
# Major External Functions/Classes: build_backtest_result
# Notes: Sharpe, max drawdown, and summary behavior preserved from engine v1.7.

from decimal import Decimal
from typing import List, Dict, Tuple

import numpy as np

from core.results import BacktestResult, TradeLog


def build_backtest_result(
    mode: str,
    capital: Decimal,
    starting_capital: Decimal,
    equity: List[Decimal],
    trades: List[TradeLog],
    regime_changes: int,
    regime_counts: Dict[str, int],
    regime_pnl: Dict[str, Decimal],
) -> Tuple[str, BacktestResult]:
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
        total_return_pct=(capital / starting_capital - 1) * 100,
        total_trades=len(trades),
        winrate=round(winrate, 1),
        sharpe=round(sharpe_ratio, 2),
        max_dd=Decimal(str(max_dd)),
        max_dd_pct=Decimal(str(max_dd_pct)),
        regime_changes=regime_changes,
        regime_counts=regime_counts,
        regime_pnl=regime_pnl,
        equity_curve=equity,
        trades=trades,
    )

    return result.summary_str() + "\n", result

# core/results_builder.py v0.2 (59 lines)