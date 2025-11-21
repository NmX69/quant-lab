# gui/optimizer_strategy_params.py
# Purpose: Strategy-parameter optimizer window (C3).
# Major External APIs:
#   - StrategyParamOptimizerWindow
#   - open_window(gui)

from __future__ import annotations

from typing import Any, Dict, List

import tkinter as tk
from tkinter import ttk, messagebox
import traceback

from core.optimizer import grid_search_strategy_params_single_asset
from gui.optimizer_base import (
    build_region_filter,
    summarize_with_region,
    parse_strategy_values,
)


class StrategyParamOptimizerWindow:
    """
    Configure and run strategy-parameter optimization for a single asset + strategy.

    Notes:
    - Always runs in NON-router mode (tests the selected strategy directly).
    - Engine risk envelope is fixed (single position_pct / risk_pct / RR).
    - User specifies up to 3 JSON-style field paths + comma-separated values.
    """

    def __init__(self, gui: Any):
        self.gui = gui

        # Own top-level window
        self.win = tk.Toplevel(gui.root)
        self.win.title("Optimize Strategy Params (single asset)")
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

        # Top-level content frame
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

        # ------------------------------------------------------------------ #
        # HEADER: asset / strategy / mode / RUN BUTTON
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

        # Run button pinned in header
        self.run_button = ttk.Button(
            header,
            text="Run Strategy Optimization",
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

        # ------------------------------------------------------------------ #
        # ENGINE ENVELOPE (read-only summary)
        # ------------------------------------------------------------------ #
        env_frame = ttk.LabelFrame(content, text="Engine Envelope (from main window)")
        env_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        env_frame.columnconfigure(0, weight=1)

        env_text = (
            f"position_pct={gui.position_pct_var.get()}    "
            f"risk_pct={gui.risk_pct_var.get()}    "
            f"reward_rr={gui.rr_var.get()}"
        )
        ttk.Label(env_frame, text=env_text).grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 6)
        )

        # ------------------------------------------------------------------ #
        # STRATEGY PARAMS (grouped, clearer labels)
        # ------------------------------------------------------------------ #
        params_frame = ttk.LabelFrame(content, text="Strategy Parameters to Optimize")
        params_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        params_frame.columnconfigure(1, weight=1)

        ttk.Label(
            params_frame,
            text="Field 1 path in strategy JSON (e.g. entry.conditions[1].below):",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(6, 2))
        self.path1_var = tk.StringVar()
        self.path1_entry = ttk.Entry(params_frame, textvariable=self.path1_var)
        self.path1_entry.grid(
            row=0, column=1, sticky="ew", padx=(0, 8), pady=(6, 2)
        )

        ttk.Label(
            params_frame,
            text="Values to try for field 1 (comma-separated):",
        ).grid(row=1, column=0, sticky="w", padx=8, pady=(2, 2))
        self.vals1_var = tk.StringVar()
        self.vals1_entry = ttk.Entry(params_frame, textvariable=self.vals1_var)
        self.vals1_entry.grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=(2, 2)
        )

        ttk.Label(
            params_frame,
            text="Field 2 path in strategy JSON (optional):",
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(2, 2))
        self.path2_var = tk.StringVar()
        self.path2_entry = ttk.Entry(params_frame, textvariable=self.path2_var)
        self.path2_entry.grid(
            row=2, column=1, sticky="ew", padx=(0, 8), pady=(2, 2)
        )

        ttk.Label(
            params_frame,
            text="Values to try for field 2 (comma-separated, optional):",
        ).grid(row=3, column=0, sticky="w", padx=8, pady=(2, 2))
        self.vals2_var = tk.StringVar()
        self.vals2_entry = ttk.Entry(params_frame, textvariable=self.vals2_var)
        self.vals2_entry.grid(
            row=3, column=1, sticky="ew", padx=(0, 8), pady=(2, 2)
        )

        ttk.Label(
            params_frame,
            text="Field 3 path in strategy JSON (optional):",
        ).grid(row=4, column=0, sticky="w", padx=8, pady=(2, 2))
        self.path3_var = tk.StringVar()
        self.path3_entry = ttk.Entry(params_frame, textvariable=self.path3_var)
        self.path3_entry.grid(
            row=4, column=1, sticky="ew", padx=(0, 8), pady=(2, 2)
        )

        ttk.Label(
            params_frame,
            text="Values to try for field 3 (comma-separated, optional):",
        ).grid(row=5, column=0, sticky="w", padx=8, pady=(2, 8))
        self.vals3_var = tk.StringVar()
        self.vals3_entry = ttk.Entry(params_frame, textvariable=self.vals3_var)
        self.vals3_entry.grid(
            row=5, column=1, sticky="ew", padx=(0, 8), pady=(2, 8)
        )

        # ------------------------------------------------------------------ #
        # REGION FILTER (C4)
        # ------------------------------------------------------------------ #
        self.filter_ctx = build_region_filter(
            parent=content,
            start_row=3,
            top_n_default="50",
            label="Region Filter (optional)",
        )

        # ------------------------------------------------------------------ #
        # STATUS + RESULTS
        # ------------------------------------------------------------------ #
        status_frame = ttk.Frame(content)
        status_frame.grid(row=4, column=0, sticky="ew", pady=(6, 4))
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="Ready.", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")

        note = ttk.Label(
            status_frame,
            text=(
                "Note: Strategy optimizer always runs in NON-router mode "
                "(it tests the selected strategy directly)."
            ),
            foreground="#8b949e",
            justify="left",
        )
        note.grid(row=1, column=0, sticky="w", pady=(2, 0))

        results_frame = ttk.LabelFrame(content, text="Results")
        results_frame.grid(row=5, column=0, sticky="nsew")
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
    # Helpers
    # ------------------------------------------------------------------ #
    def _build_strategy_param_grid(self) -> Dict[str, List[Any]]:
        """
        Read up to 3 (field_path, values) pairs from the UI and produce a
        strategy_param_grid dict suitable for core.optimizer.
        """
        param_grid: Dict[str, List[Any]] = {}

        p1 = self.path1_var.get().strip()
        v1 = self.vals1_var.get().strip()
        if p1 and v1:
            param_grid[p1] = parse_strategy_values(v1)

        p2 = self.path2_var.get().strip()
        v2 = self.vals2_var.get().strip()
        if p2 and v2:
            param_grid[p2] = parse_strategy_values(v2)

        p3 = self.path3_var.get().strip()
        v3 = self.vals3_var.get().strip()
        if p3 and v3:
            param_grid[p3] = parse_strategy_values(v3)

        return param_grid

    # ------------------------------------------------------------------ #
    # Core action
    # ------------------------------------------------------------------ #
    def run_optimization(self) -> None:
        if self.status_label is None or self.results_text is None:
            return

        self.status_label.config(text="Running strategy-parameter optimization…")
        self.win.config(cursor="watch")
        self.win.update_idletasks()

        try:
            asset_label = self.asset_var.get()
            if not asset_label:
                messagebox.showerror("Error", "Asset is required")
                self.status_label.config(text="Error: missing asset")
                return

            # Labels are "ASSET timeframe" (e.g. "XRPUSDT 1h")
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

            strategy_param_grid = self._build_strategy_param_grid()
            if not strategy_param_grid:
                messagebox.showerror(
                    "Error",
                    "You must specify at least one field path and its values.",
                )
                self.status_label.config(text="Error: no parameters specified")
                return

            # Fixed engine envelope from main GUI
            position_pct = float(self.gui.position_pct_var.get())
            risk_pct = float(self.gui.risk_pct_var.get())
            reward_rr = float(self.gui.rr_var.get())

            df_res = grid_search_strategy_params_single_asset(
                asset_file=asset_file,
                strategy_name=self.strat_var.get(),
                mode=self.mode_var.get(),
                strategy_param_grid=strategy_param_grid,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
                max_candles=int(self.gui.candles_var.get() or 0),
            )

            self.results_text.delete("1.0", tk.END)
            if df_res is None or df_res.empty:
                self.results_text.insert("1.0", "No results.\n")
                self.status_label.config(
                    text="Strategy optimization completed. No results."
                )
                return

            df_show = summarize_with_region(
                df_res,
                filter_ctx=self.filter_ctx,
                status_label=self.status_label,
                status_prefix="Strategy optimization completed",
            )
            self.results_text.insert("1.0", df_show.to_string(index=False) + "\n")

        except Exception:
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(
                "1.0", "Strategy optimization failed:\n\n" + traceback.format_exc()
            )
            self.status_label.config(text="Strategy optimization failed.")
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
    StrategyParamOptimizerWindow(gui).show()


# gui/optimizer_strategy_params.py v0.4 (399 lines)
