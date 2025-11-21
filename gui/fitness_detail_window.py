# gui/fitness_detail_window.py
# Purpose: Detail popup for a single fitness matrix row (Phase D).
# Major External Classes:
#   - FitnessDetailWindow(tk.Toplevel)
# Notes: Non-modal; called from FitnessTabbedWindow on row double-click.

from __future__ import annotations

from typing import Any, Dict, Optional
from numbers import Number

import tkinter as tk
from tkinter import ttk


class FitnessDetailWindow(tk.Toplevel):
    """Popup detail view for a single fitness row, with strong visual separation."""

    def __init__(
        self,
        owner: tk.Widget,
        row_data: Dict[str, Any],
        title: str = "Fitness Row Details",
    ) -> None:
        if isinstance(owner, (tk.Tk, tk.Toplevel)):
            parent = owner
        elif hasattr(owner, "winfo_toplevel"):
            parent = owner.winfo_toplevel()
        else:
            parent = tk._default_root  # type: ignore[assignment]

        super().__init__(parent)

        self.owner = owner
        self.row_data = row_data

        self.title(title)

        self.configure(
            background="#333333",
            highlightthickness=6,
            highlightbackground="#ffff00",
            highlightcolor="#ffff00",
        )

        # Normal toplevel: keep maximize button available
        # (no self.transient(parent) here)
        self.resizable(True, True)

        self.bind("<Escape>", lambda _e: self.destroy())

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Scrollable content via Canvas + inner frame
        outer = ttk.Frame(self)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            outer,
            background="#333333",
            highlightthickness=0,
            borderwidth=0,
        )
        v_scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")

        self._canvas = canvas

        container = ttk.Frame(canvas)
        self._container = container

        canvas_window = canvas.create_window((0, 0), window=container, anchor="nw")

        def _on_frame_config(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        container.bind("<Configure>", _on_frame_config)

        def _on_canvas_config(event):
            canvas.itemconfigure(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_config)

        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        self._build_sections(container)
        self._center_on_parent()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _build_sections(self, parent: ttk.Frame) -> None:
        """
        Layout: 2×2 grid for the four main sections,
        then buttons row at the bottom spanning both columns.
        """
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Top-left: Summary
        summary_frame = ttk.LabelFrame(parent, text="Summary")
        summary_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=(0, 6))
        summary_frame.columnconfigure(1, weight=1)
        self._populate_summary(summary_frame)

        # Top-right: Sizing & Config
        sizing_frame = ttk.LabelFrame(parent, text="Sizing & Config")
        sizing_frame.grid(row=0, column=1, sticky="nsew", padx=4, pady=(0, 6))
        sizing_frame.columnconfigure(1, weight=1)
        self._populate_sizing(sizing_frame)

        # Bottom-left: Performance & Risk
        perf_frame = ttk.LabelFrame(parent, text="Performance & Risk")
        perf_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 6))
        perf_frame.columnconfigure(1, weight=1)
        self._populate_performance(perf_frame)

        # Bottom-right: Stability & Regime Stats
        stab_frame = ttk.LabelFrame(parent, text="Stability & Regime Stats")
        stab_frame.grid(row=1, column=1, sticky="nsew", padx=4, pady=(0, 6))
        stab_frame.columnconfigure(1, weight=1)
        self._populate_stability(stab_frame)

        # Buttons row
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="e", padx=4, pady=(6, 6))
        ttk.Button(btn_frame, text="Close", command=self.destroy).grid(row=0, column=0, padx=4, pady=2)

    def _format_3dp(self, value: Any) -> str:
        """Format numeric to 3 decimals, keep ints as ints."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, Number):
            if isinstance(value, int):
                return str(value)
            try:
                return f"{float(value):.3f}"
            except Exception:
                return str(value)
        return str(value)

    def _add_row(
        self,
        frame: ttk.Frame,
        row: int,
        label: str,
        value: Optional[Any],
    ) -> int:
        if value is None:
            return row

        text_value = self._format_3dp(value)

        # Label in default style
        ttk.Label(
            frame,
            text=f"{label}:",
        ).grid(row=row, column=0, sticky="w", padx=(6, 4), pady=2)

        # Value in light blue
        ttk.Label(
            frame,
            text=text_value,
            foreground="#66ccff",
        ).grid(row=row, column=1, sticky="w", padx=(0, 6), pady=2)

        return row + 1

    # ------------------------------------------------------------------
    # Section population
    # ------------------------------------------------------------------

    def _populate_summary(self, frame: ttk.Frame) -> None:
        d = self.row_data
        r = 0

        asset = d.get("asset")
        timeframe = d.get("timeframe")
        strategy = d.get("strategy_name") or d.get("strategy") or d.get("strategy_key")
        mode = d.get("mode")
        use_router = d.get("use_router")
        fitness = d.get("fitness_score")
        expectancy = d.get("expectancy_R")

        asset_tf = None
        if asset or timeframe:
            asset_tf = f"{asset or ''}  /  {timeframe or ''}".strip()

        r = self._add_row(frame, r, "Strategy", strategy)
        r = self._add_row(frame, r, "Asset / Timeframe", asset_tf)
        r = self._add_row(frame, r, "Mode", mode)
        if use_router is not None:
            router_text = "Yes" if bool(use_router) else "No"
            r = self._add_row(frame, r, "Regime Router", router_text)
        r = self._add_row(frame, r, "Fitness Score", fitness)
        r = self._add_row(frame, r, "Expectancy (R)", expectancy)

    def _populate_performance(self, frame: ttk.Frame) -> None:
        d = self.row_data
        r = 0

        r = self._add_row(frame, r, "Final Equity", d.get("final_equity"))
        r = self._add_row(frame, r, "Total Return %", d.get("total_return_pct"))
        r = self._add_row(frame, r, "Total Trades", d.get("total_trades"))
        r = self._add_row(frame, r, "Winrate %", d.get("winrate") or d.get("winrate_pct"))
        r = self._add_row(frame, r, "Max Drawdown", d.get("max_dd"))
        r = self._add_row(frame, r, "Max Drawdown %", d.get("max_dd_pct"))
        r = self._add_row(frame, r, "Sharpe", d.get("sharpe"))
        r = self._add_row(frame, r, "Sortino", d.get("sortino"))
        r = self._add_row(frame, r, "MAR", d.get("mar"))
        r = self._add_row(frame, r, "Expectancy / DD", d.get("expectancy_per_dd"))

    def _populate_sizing(self, frame: ttk.Frame) -> None:
        d = self.row_data
        r = 0

        r = self._add_row(frame, r, "Position % of Equity", d.get("position_pct"))
        r = self._add_row(frame, r, "Risk % per Trade", d.get("risk_pct"))

        rr = d.get("reward_rr")
        if rr is None:
            rr_text = "Strategy default"
        else:
            rr_text = self._format_3dp(rr)
        r = self._add_row(frame, r, "Reward:Risk (RR)", rr_text)

        r = self._add_row(frame, r, "Tag", d.get("tag"))

    def _populate_stability(self, frame: ttk.Frame) -> None:
        d = self.row_data
        r = 0

        r = self._add_row(frame, r, "Stability Score", d.get("stability_score"))
        r = self._add_row(frame, r, "Trade Density", d.get("trade_density"))
        r = self._add_row(frame, r, "Regime Std", d.get("regime_std"))
        r = self._add_row(frame, r, "Regime CV", d.get("regime_cv"))
        r = self._add_row(frame, r, "Worst Regime", d.get("worst_regime"))
        r = self._add_row(frame, r, "Worst Regime Expectancy (R)", d.get("worst_regime_E"))
        r = self._add_row(frame, r, "Regime Changes", d.get("regime_changes"))

        regimes = [
            ("Ranging", "ranging"),
            ("Trending Up", "trending_up"),
            ("Trending Down", "trending_down"),
        ]

        for title, key in regimes:
            candles_key = f"reg_{key}_candles"
            pnl_key = f"reg_{key}_pnl_pct"
            trades_key = f"reg_{key}_trades"
            win_key = f"reg_{key}_winrate"
            exp_key = f"reg_{key}_expectancy_R"

            if (
                candles_key not in d
                and pnl_key not in d
                and trades_key not in d
                and win_key not in d
                and exp_key not in d
            ):
                continue

            ttk.Label(
                frame,
                text=title,
                font=("TkDefaultFont", 9, "bold"),
            ).grid(row=r, column=0, columnspan=2, sticky="w", padx=(6, 4), pady=(8, 2))
            r += 1

            lines = []

            candles = d.get(candles_key)
            frac = d.get(f"reg_{key}_candles_frac")
            pnl = d.get(pnl_key)
            trades = d.get(trades_key)
            winrate = d.get(win_key)
            exp = d.get(exp_key)

            if candles is not None or frac is not None:
                c_text = self._format_3dp(candles) if candles is not None else "?"
                f_text = self._format_3dp(frac) if frac is not None else "?"
                lines.append(f"Candles: {c_text} ({f_text})")
            if pnl is not None:
                pnl_text = self._format_3dp(pnl)
                lines.append(f"PnL: {pnl_text}%")
            if trades is not None or winrate is not None or exp is not None:
                parts = []
                if trades is not None:
                    parts.append(f"Trades: {self._format_3dp(trades)}")
                if winrate is not None:
                    parts.append(f"Winrate: {self._format_3dp(winrate)}%")
                if exp is not None:
                    parts.append(f"Exp: {self._format_3dp(exp)} R")
                lines.append(" | ".join(parts))

            if lines:
                ttk.Label(
                    frame,
                    text="\n".join(lines),
                    justify="left",
                    foreground="#66ccff",  # numbers-heavy text in light blue
                ).grid(
                    row=r,
                    column=0,
                    columnspan=2,
                    sticky="w",
                    padx=(12, 6),
                    pady=(0, 2),
                )
                r += 1

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        try:
            parent = self.master
            if parent is None:
                return
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except Exception:
            return

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # Make it bigger by default, but keep margins from screen edges.
        w = self.winfo_width()
        h = self.winfo_height()

        # Roughly "twice as wide and about 7 rows taller" vs prior 600x400
        w = max(w, 900)
        h = max(h, 600)

        w = min(w, sw - 80)
        h = min(h, sh - 80)

        x = px + (pw - w) // 2
        y = py + (ph - h) // 2

        self.geometry(f"{w}x{h}+{x}+{y}")


# gui/fitness_detail_window.py v0.3 (359 lines)
