# gui/results_display.py
# Purpose: Handle equity plotting and textual formatting of multi-run summaries.
# Major External Functions/Classes: plot_equity_curve, format_all_strategies_summary, format_all_assets_summary
# Notes: GUI-agnostic helper functions; GUI passes in its Figure and trades/DataFrames.

from decimal import Decimal

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure


def plot_equity_curve(fig: Figure, trades) -> None:
    """
    Plot equity curve onto the provided Matplotlib Figure, using TradeLog list.
    """
    ax = fig.add_subplot(111)
    ax.clear()

    equity = [Decimal("100.0")]
    capital = Decimal("100.0")
    for t in trades:
        if t.exit_reason != "end_of_simulation":
            capital += t.pnl
        equity.append(capital)

    ax.plot(equity, color="#ffea00", linewidth=2, label="Equity")
    ax.set_facecolor("#0d1b2a")
    ax.grid(True, color="#1f6aa5", linestyle="--", alpha=0.5)
    ax.set_title("Equity Curve", color="white", fontsize=12)
    ax.set_xlabel("Trade #", color="white", fontsize=10)
    ax.set_ylabel("Value ($)", color="white", fontsize=10)
    ax.tick_params(colors="white", labelsize=9)
    ax.legend(facecolor="#1f1f1f", edgecolor="#ffea00", labelcolor="white", fontsize=9)
    fig.tight_layout()


def format_all_strategies_summary(df_res: pd.DataFrame) -> str:
    if df_res.empty:
        return "No valid results.\n"
    return "All Strategies Summary:\n" + df_res.to_string(index=False) + "\n\n"


def format_all_assets_summary(df_res: pd.DataFrame) -> str:
    if df_res.empty:
        return "No valid results.\n"
    return "All Assets Summary:\n" + df_res.to_string(index=False) + "\n\n"

# gui/results_display.py v1.0 (49 lines)
