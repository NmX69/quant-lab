# core/results.py
# PHASE A 100% — full canonical research-grade TradeLog with all required fields

from dataclasses import dataclass, asdict
from typing import List, Dict
from decimal import Decimal
import numpy as np
import pandas as pd
import os
from datetime import datetime

@dataclass
class TradeLog:
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

    # === PHASE A CANONICAL FIELDS ===
    pnl_R: float = 0.0
    reward_multiple: float = 1.5
    stop_distance_pct: float = 0.0
    take_profit_multiple: float = 1.5
    hold_time_hours: float = 0.0
    trade_type: str = ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["entry_ts"] = d["entry_ts"]
        d["exit_ts"] = d["exit_ts"]
        return d


@dataclass
class BacktestResult:
    asset: str
    mode: str
    final_equity: Decimal
    total_return_pct: Decimal
    total_trades: int
    winrate: float
    sharpe: float
    max_dd: Decimal
    max_dd_pct: Decimal
    regime_changes: int
    regime_counts: Dict[str, int]
    regime_pnl: Dict[str, Decimal]
    equity_curve: List[Decimal]
    trades: List[TradeLog]

    def _time_under_water_hours(self) -> float:
        equity = [float(e) for e in self.equity_curve]
        if not equity:
            return 0.0
        peak = equity[0]
        under = 0
        for v in equity[1:]:
            if v < peak:
                under += 1
            else:
                peak = max(peak, v)
        return round(under, 1)

    def save_trades(self, output_dir: str = "results"):
        os.makedirs(output_dir, exist_ok=True)
        df = pd.DataFrame([t.to_dict() for t in self.trades])
        filename = f"{self.asset}_{self.mode}.csv"
        df.to_csv(os.path.join(output_dir, filename), index=False)

    def summary_str(self) -> str:
        lines = [
            "=" * 60,
            f"BACKTEST (router) – {self.asset}",
            "=" * 60,
            f"Final: ${float(self.final_equity):.2f}",
            f"Return: {float(self.total_return_pct):+.2f}%",
            f"Trades: {self.total_trades}",
            f"Winrate: {self.winrate:.1f}%",
            f"Sharpe: {self.sharpe:.2f}",
            f"Time Under Water: {self._time_under_water_hours():.1f}h",
            f"Max DD: ${float(self.max_dd):.2f} ({float(self.max_dd_pct):.2f}%)",
            f"Total Regime Changes: {self.regime_changes}",
            "Regimes:",
        ]
        for regime, count in self.regime_counts.items():
            pnl = self.regime_pnl.get(regime, Decimal("0"))
            pnl_pct = float(pnl) / 100.0 * 100 if pnl != 0 else 0.0
            lines.append(f"  {regime}: {count} candles | PNL: ${float(pnl):+.4f} ({pnl_pct:+.2f}%)")
        lines.append("=" * 60)
        return "\n".join(lines)


# core/results.py v0.2