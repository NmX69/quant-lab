# core/results.py
# PHASE f5 — PORTFOLIO SUMMARY + WINRATE + SHARPE + SUMMARY.CSV

from dataclasses import dataclass, asdict
from typing import List, Dict
from decimal import Decimal
import numpy as np

import pandas as pd
import os
import numpy as np

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

    def to_dict(self) -> Dict:
        return asdict(self)

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
    equity_curve: List[Decimal]  # NEW: for sharpe
    trades: List[TradeLog]

    def save_trades(self, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)
        df = pd.DataFrame([t.to_dict() for t in self.trades])
        filename = f"{self.asset.replace('/', '_')}_{self.mode}.csv"
        df.to_csv(os.path.join(output_dir, filename), index=False)

    def summary_str(self) -> str:
        total_pnl = self.final_equity - Decimal("100.0")
        lines = [
            "=" * 60,
            f"BACKTEST: {self.asset} – {self.mode}",
            "=" * 60,
            f"Final: ${self.final_equity:,.2f}",
            f"Return: {self.total_return_pct:+.2f}%",
            f"Trades: {self.total_trades}",
            f"Winrate: {self.winrate:.1f}%",
            f"Sharpe: {self.sharpe:.2f}",
            f"Max DD: ${self.max_dd:,.2f} ({self.max_dd_pct:.2f}%)",
            f"Total Regime Changes: {self.regime_changes}",
            "Regimes:",
        ]
        for regime, count in self.regime_counts.items():
            pnl = self.regime_pnl.get(regime, Decimal("0"))
            pnl_pct = (pnl / Decimal("100.0")) * 100 if pnl != 0 else Decimal("0")
            lines.append(f"  {regime}: {count} candles | PNL: ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        lines.append("=" * 60)
        return "\n".join(lines)