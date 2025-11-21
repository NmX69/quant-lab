# gui/optimizer_envelope_single.py
# Purpose: Single-asset envelope optimizer window (C1).
# Major External APIs:
#   - SingleAssetOptimizerWindow
#   - open_window(gui)

from __future__ import annotations

from typing import Any, Dict, List

import tkinter as tk
from tkinter import ttk, messagebox
import traceback

from core.optimizer import grid_search_single_asset
from gui.optimizer_base import (
    build_region_filter,
    summarize_with_region,
    parse_float_list,
)


class SingleAssetOptimizerWindow:
    """
    Optimize engine-level envelope (position_pct, risk_pct, reward_rr)
    for a single asset + strategy, optionally with C4 region filter.
    """

    def __init__(self, gui: Any):
        self.gui = gui

        # Create our own top-level window, fully controlled
        self.win = tk.Toplevel(gui.root)
        self.win.title("Optimize Current Asset")
        self.win.configure(bg="#0d1117")

        # Start maximized where possible
        try:
            self.win.state("zoomed")
        except Exception:
            try:
                self.win.attributes("-zoomed", True)
            except Exception:
                pass
        self.win.resizable(True, True)

        # Top-level grid: single content frame that scales
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)

        content = ttk.Frame(self.win)
        content.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        content.columnconfigure(0, weight=1)
        for r in range(5):
            content.rowconfigure(r, weight=0)
        content.rowconfigure(4, weight=1)  # results row stretches

        # Defaults from main GUI
        default_asset_label = gui.file_var.get()
        default_strategy = gui.strategy_var.get()
        default_mode = gui.mode_var.get()
        default_use_router = gui.use_router_var.get()

        # ------------------------------------------------------------------ #
        # HEADER: asset / strategy / mode / router / RUN BUTTON
        # ------------------------------------------------------------------ #
        header = ttk.Frame(content)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=0)

        ttk.Label(header, text="Asset:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 2)
        )
        self.asset_var = tk.StringVar(value=default_asset_label)
        asset_values = list(gui.file_combo["values"])
        self.asset_combo = ttk.Combobox(
            header,
            textvariable=self.asset_var,
            values=asset_values,
            state="readonly",
            width=50,
        )
        self.asset_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(0, 2))

        # RUN BUTTON pinned in the header so it never scrolls off-screen
        self.run_button = ttk.Button(
            header,
            text="Run Optimization",
            command=self.run_optimization,
        )
        self.run_button.grid(
            row=0,
            column=2,
            rowspan=2,
            sticky="nsew",
            padx=(0, 0),
            pady=(0, 2),
        )

        ttk.Label(header, text="Strategy:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(2, 2)
        )
        self.strat_var = tk.StringVar(value=default_strategy)
        strat_values = list(gui.strategy_combo["values"])
        self.strat_combo = ttk.Combobox(
            header,
            textvariable=self.strat_var,
            values=strat_values,
            state="readonly",
            width=40,
        )
        self.strat_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(2, 2))

        ttk.Label(header, text="Mode:").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=(2, 2)
        )
        self.mode_var = tk.StringVar(value=default_mode)
        self.mode_combo = ttk.Combobox(
            header,
            textvariable=self.mode_var,
            values=["conservative", "balanced", "aggressive"],
            state="readonly",
            width=20,
        )
        self.mode_combo.grid(row=2, column=1, sticky="w", padx=(0, 8), pady=(2, 2))

        self.use_router_var = tk.BooleanVar(value=default_use_router)
        ttk.Checkbutton(
            header,
            text="Use Regime Router (use current router mappings)",
            variable=self.use_router_var,
        ).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="w",
            padx=(0, 8),
            pady=(4, 0),
        )

        # ------------------------------------------------------------------ #
        # OPTIMIZATION PARAMETERS (nicely grouped)
        # ------------------------------------------------------------------ #
        params_frame = ttk.LabelFrame(content, text="Optimization Parameters")
        params_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        params_frame.columnconfigure(1, weight=1)

        ttk.Label(params_frame, text="position_pct values (comma-separated):").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 2)
        )
        pos_default = f"{float(gui.position_pct_var.get()):.1f}"
        self.pos_entry = ttk.Entry(params_frame)
        self.pos_entry.insert(0, pos_default)
        self.pos_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, 8),
            pady=(6, 2),
        )

        ttk.Label(params_frame, text="risk_pct values (comma-separated):").grid(
            row=1, column=0, sticky="w", padx=8, pady=(2, 2)
        )
        risk_default = f"{float(gui.risk_pct_var.get()):.2f}"
        self.risk_entry = ttk.Entry(params_frame)
        self.risk_entry.insert(0, risk_default)
        self.risk_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 8),
            pady=(2, 2),
        )

        ttk.Label(params_frame, text="reward_rr values (comma-separated):").grid(
            row=2, column=0, sticky="w", padx=8, pady=(2, 2)
        )
        rr_default = f"{float(gui.rr_var.get()):.2f}"
        self.rr_entry = ttk.Entry(params_frame)
        self.rr_entry.insert(0, rr_default)
        self.rr_entry.grid(
            row=2,
            column=1,
            sticky="ew",
            padx=(0, 8),
            pady=(2, 2),
        )

        ttk.Label(params_frame, text="Max candles (0 = all):").grid(
            row=3, column=0, sticky="w", padx=8, pady=(2, 8)
        )
        max_c_default = str(gui.candles_var.get())
        self.max_c_entry = ttk.Entry(params_frame, width=12)
        self.max_c_entry.insert(0, max_c_default)
        self.max_c_entry.grid(
            row=3,
            column=1,
            sticky="w",
            padx=(0, 8),
            pady=(2, 8),
        )

        # ------------------------------------------------------------------ #
        # REGION FILTER (C4)
        # ------------------------------------------------------------------ #
        # Keep using the shared helper so behavior stays consistent.
        # It already draws a nice framed block.
        self.filter_ctx = build_region_filter(
            parent=content,
            start_row=2,
            top_n_default="50",
        )

        # ------------------------------------------------------------------ #
        # STATUS + RESULTS AREA
        # ------------------------------------------------------------------ #
        status_frame = ttk.Frame(content)
        status_frame.grid(row=3, column=0, sticky="ew", pady=(6, 4))
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")

        results_frame = ttk.LabelFrame(content, text="Results")
        results_frame.grid(row=4, column=0, sticky="nsew")
        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)

        self.results_text = tk.Text(
            results_frame,
            wrap="none",
            height=18,
            bg="#0d1117",
            fg="#c9d1d9",
            insertbackground="#c9d1d9",
            font=("Consolas", 10),
            borderwidth=0,
            highlightthickness=0,
        )
        self.results_text.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            results_frame, orient="vertical", command=self.results_text.yview
        )
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(
            results_frame, orient="horizontal", command=self.results_text.xview
        )
        x_scroll.grid(row=1, column=0, sticky="ew")

        self.results_text.config(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

    # ------------------------------------------------------------------ #
    # Core action
    # ------------------------------------------------------------------ #
    def run_optimization(self) -> None:
        if self.status_label is None or self.results_text is None:
            return

        self.status_label.config(text="Running optimization…")
        self.win.config(cursor="watch")
        self.win.update_idletasks()

        try:
            asset_label = self.asset_var.get()
            if not asset_label:
                messagebox.showerror("Error", "Asset is required")
                self.status_label.config(text="Error: missing asset")
                return

            # Labels are "ASSET timeframe" (e.g. "ADAUSDT 1h")
            parts = asset_label.split()
            asset = parts[0]
            timeframe = (
                parts[1] if len(parts) > 1 else getattr(self.gui, "timeframe_var", None)
            )
            if hasattr(timeframe, "get"):
                timeframe = timeframe.get()
            if not timeframe:
                timeframe = "1h"

            asset_file = f"{asset}_{timeframe}.csv"

            # Build param grid from text entries
            param_grid: Dict[str, List[float]] = {
                "position_pct": parse_float_list(
                    self.pos_entry.get(),
                    float(self.gui.position_pct_var.get()),
                ),
                "risk_pct": parse_float_list(
                    self.risk_entry.get(),
                    float(self.gui.risk_pct_var.get()),
                ),
                "reward_rr": parse_float_list(
                    self.rr_entry.get(),
                    float(self.gui.rr_var.get()),
                ),
            }

            try:
                max_c = int(self.max_c_entry.get())
            except Exception:
                max_c = 0

            df_res = grid_search_single_asset(
                asset_file=asset_file,
                strategy_name=self.strat_var.get(),
                mode=self.mode_var.get(),
                use_router=self.use_router_var.get(),
                param_grid=param_grid,
                max_candles=max_c,
            )

            self.results_text.delete("1.0", tk.END)
            if df_res is None or df_res.empty:
                self.results_text.insert("1.0", "No results.\n")
                self.status_label.config(text="Optimization completed. No results.")
                return

            df_show = summarize_with_region(
                df_res,
                filter_ctx=self.filter_ctx,
                status_label=self.status_label,
                status_prefix="Optimization completed",
            )
            self.results_text.insert("1.0", df_show.to_string(index=False) + "\n")

        except Exception:
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(
                "1.0", "Optimization failed:\n\n" + traceback.format_exc()
            )
            self.status_label.config(text="Optimization failed.")
        finally:
            self.win.config(cursor="")
            self.win.update_idletasks()

    # ------------------------------------------------------------------ #
    # Show helper for menu entry
    # ------------------------------------------------------------------ #
    def show(self) -> None:
        self.win.transient(self.gui.root)
        self.win.focus_set()
        self.win.grab_set()


def open_window(gui: Any) -> None:
    """
    Backwards-compatible entrypoint for the existing menu wiring.
    """
    SingleAssetOptimizerWindow(gui).show()


# gui/optimizer_envelope_single.py v0.6 (356 lines)
