# gui/backtester_gui.py
# Purpose: Define BacktesterGUI and connect UI elements to core backtest logic.
# Major External Functions/Classes: BacktesterGUI
# Notes: Layout and styles live in gui/layout.py and gui/styles.py respectively.

import json
import os
import sys
import traceback
from typing import Any, Dict, Optional, List

import tkinter as tk
from tkinter import ttk, messagebox

from core.config_manager import (
    load_config,
    save_config,
    MANIFEST_FILE,
)
from core.backtest_runner import (
    run_single_backtest,
    run_all_strategies_backtest,
    run_all_assets_backtest,
)
from core.strategy_loader import load_strategies, list_strategies
from core.reporting import build_report
from gui.styles import setup_styles
from gui.layout import create_left_panel, create_right_panel
from core.results_display import (
    plot_equity_curve,
    format_all_strategies_summary,
    format_all_assets_summary,
)

from gui import optimizer_envelope_single
from gui import optimizer_envelope_all
from gui import optimizer_strategy_params
from gui.fitness_window import FitnessTabbedWindow


class BacktesterGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Regime-Aware Backtester")
        self.root.geometry("1700x1000")
        try:
            self.root.state("zoomed")
        except Exception:
            # On some platforms, zoomed may not exist; ignore.
            pass
        self.root.configure(bg="#0d1117")

        # Save config when window is closed via the X button
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.df = None
        self.trades: List[Any] = []
        self.summary: str = ""
        self.latest_report: Dict[str, Any] = {}
        self.latest_report_label: str = ""
        self.report_available: bool = False

        self.config: Dict[str, Any] = load_config()

        self.mode_var = tk.StringVar(value=self.config.get("mode", "balanced"))

        setup_styles()
        self._create_menu()
        create_left_panel(self)
        create_right_panel(self)

        # Strategies, data, and UI initial state
        self.load_strategies()
        self.scan_data_files()
        self._toggle_router_ui()
        self._toggle_equity_area()

    # ------------------------------------------------------------------ #
    # MENU / REPORTS
    # ------------------------------------------------------------------ #
    def _create_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # Data menu
        data_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Data", menu=data_menu)
        data_menu.add_command(label="Rescan Data", command=self.scan_data_files)

        # Reports menu (Phase B)
        reports_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Reports", menu=reports_menu)
        reports_menu.add_command(
            label="Show Last Analytics",
            command=self.show_last_analytics,
            state="disabled",
        )

        # Optimize menu (Phase C)
        optimizer_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Optimize", menu=optimizer_menu)
        optimizer_menu.add_command(
            label="Optimize Current Asset",
            command=self.open_single_optimizer_window,
        )
        optimizer_menu.add_command(
            label="Optimize All Assets (timeframe)",
            command=self.open_all_assets_optimizer_window,
        )
        optimizer_menu.add_command(
            label="Optimize Strategy Params (single asset)",
            command=self.open_strategy_param_optimizer_window,
        )

        # Fitness menu (Phase D)
        fitness_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Fitness", menu=fitness_menu)
        fitness_menu.add_command(
            label="Open Fitness Scanner",
            command=self.open_fitness_scanner_window,
        )

        self.reports_menu = reports_menu

    # ------------------------------------------------------------------ #
    # CONFIG BUILD/SAVE
    # ------------------------------------------------------------------ #
    def _build_config_dict(self) -> Dict[str, Any]:
        """
        Build a dict representing the current GUI state for persistence.

        NOTE:
        - data_file is persisted as an actual filename (e.g. "BTCUSDT_1h.csv"),
          NOT the combo label, so that scan_data_files() can reconstruct the
          correct "ASSET timeframe" option on reload.
        - This function is the single source of truth for what we write to
          config.json.
        """
        selection = self.file_var.get()
        timeframe = self.timeframe_var.get()
        data_file = ""

        if selection:
            parts = selection.split()
            asset = parts[0]
            if len(parts) > 1:
                timeframe = parts[1]
            if asset and timeframe:
                data_file = f"{asset}_{timeframe}.csv"

        return {
            "data_file": data_file or self.config.get("data_file", ""),
            "timeframe": timeframe,
            "strategy": self.strategy_var.get(),
            "mode": self.mode_var.get(),
            "use_router": self.use_router_var.get(),
            "trending_up_strategy": self.trending_up_var.get(),
            "trending_down_strategy": self.trending_down_var.get(),
            "ranging_strategy": self.ranging_var.get(),
            "position_pct": self.position_pct_var.get(),
            "risk_pct": self.risk_pct_var.get(),
            "reward_rr": self.rr_var.get(),
            "candles": self.candles_var.get(),
            "run_mode": self.run_mode_var.get(),
            "show_equity": self.equity_var.get(),
        }

    def save_current_config(self) -> None:
        cfg = self._build_config_dict()
        save_config(cfg)

    # ------------------------------------------------------------------ #
    # ANALYTICS POPUP
    # ------------------------------------------------------------------ #
    def show_last_analytics(self) -> None:
        """Show the last backtest analytics in a simple text popup."""
        if not self.report_available or not self.latest_report:
            messagebox.showinfo("Reports", "No report available. Run a backtest first.")
            return

        win = tk.Toplevel(self.root)
        win.title("Last Backtest Analytics")
        win.configure(bg="#0d1117")

        label_text = self.latest_report_label or "Last Backtest"
        ttk.Label(win, text=label_text).pack(anchor="w", padx=10, pady=(10, 5))

        text = tk.Text(
            win,
            wrap="word",
            width=100,
            height=30,
            bg="#0d1117",
            fg="#c9d1d9",
            insertbackground="#c9d1d9",
            font=("Consolas", 11),
        )
        text.pack(fill="both", expand=True, padx=10, pady=10)

        report = self.latest_report
        meta = report.get("meta", {})
        risk = report.get("risk", {})
        streaks = report.get("streaks", {})
        drawdown = report.get("drawdown", {})
        regimes = report.get("regimes", {})

        lines: List[str] = []
        lines.append("META")
        for k, v in meta.items():
            lines.append(f"  {k}: {v}")

        lines.append("\nRISK")
        for k, v in risk.items():
            lines.append(f"  {k}: {v}")

        lines.append("\nSTREAKS")
        for k, v in streaks.items():
            lines.append(f"  {k}: {v}")

        lines.append("\nDRAWDOWN")
        for k, v in drawdown.items():
            if not isinstance(v, list):
                lines.append(f"  {k}: {v}")

        lines.append("\nREGIMES")
        for name, stats in regimes.items():
            lines.append(f"  {name}:")
            for key, val in stats.items():
                lines.append(f"    {key}: {val}")

        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # DATA / MANIFEST HANDLING
    # ------------------------------------------------------------------ #
    def scan_data_files(self) -> None:
        """
        Scan manifest.json for available assets/timeframes and repopulate combo.

        Supports either:
          { "pairs": { "BTCUSDT": {"1h": "...", ...}, ... } }
        or:
          { "BTCUSDT": {"1h": "...", ...}, ... }
        """
        try:
            with open(MANIFEST_FILE, "r") as f:
                manifest = json.load(f)
        except Exception:
            return

        if isinstance(manifest, dict) and "pairs" in manifest and isinstance(
            manifest["pairs"], dict
        ):
            pairs = manifest["pairs"]
        else:
            pairs = manifest

        values: List[str] = []
        for asset, tf_data in pairs.items():
            if isinstance(tf_data, dict):
                for tf in sorted(tf_data.keys()):
                    values.append(f"{asset} {tf}")
            else:
                values.append(asset)

        self.file_combo["values"] = values

        # Try to restore last selection (supports old and new formats)
        last_file = self.config.get("data_file", "")
        last_tf = self.config.get("timeframe", "1h")

        last_base = ""
        if last_file:
            if " " in last_file and not last_file.endswith(".csv"):
                # Old style persisted value like "ADAUSDT 1h"
                parts = last_file.split()
                last_base = parts[0]
                if len(parts) > 1:
                    last_tf = parts[1]
            else:
                # New style filename, e.g. "BTCUSDT_1h.csv"
                base = last_file.replace(".csv", "")
                if "_" in base:
                    asset_part, tf_part = base.rsplit("_", 1)
                    last_base = asset_part
                    # If timeframe wasn't explicitly set, fall back to filename
                    if not self.config.get("timeframe"):
                        last_tf = tf_part
                else:
                    last_base = base

        last_combined = f"{last_base} {last_tf}" if last_base else ""

        if last_combined in values:
            self.file_var.set(last_combined)
        elif values:
            self.file_var.set(values[0])

    def _get_available_timeframes(self) -> List[str]:
        """
        Return sorted list of available timeframes from manifest.json.
        Works with both "pairs"-wrapped and flat manifests.
        """
        try:
            with open(MANIFEST_FILE, "r") as f:
                manifest = json.load(f)
        except Exception:
            return ["1h"]

        if isinstance(manifest, dict) and "pairs" in manifest and isinstance(
            manifest["pairs"], dict
        ):
            pairs = manifest["pairs"]
        else:
            pairs = manifest

        tfs = set()
        for _, tf_data in pairs.items():
            if isinstance(tf_data, dict):
                for tf in tf_data.keys():
                    tfs.add(tf)

        return sorted(tfs) or ["1h"]

    # ------------------------------------------------------------------ #
    # STRATEGY LOADING
    # ------------------------------------------------------------------ #
    def load_strategies(self) -> None:
        """
        Load strategies and populate the strategy-related combos.

        Uses the global registry from core.strategy_loader; list_strategies()
        no longer takes arguments.
        """
        load_strategies()
        names = list_strategies()
        self.strategy_combo["values"] = names

        # Main strategy selection
        if self.config.get("strategy") in names:
            self.strategy_var.set(self.config["strategy"])
        elif names:
            self.strategy_var.set(names[0])

        # Router strategies
        self.trending_up_combo["values"] = names
        self.trending_down_combo["values"] = names
        self.ranging_combo["values"] = names

        if self.config.get("trending_up_strategy") in names:
            self.trending_up_var.set(self.config["trending_up_strategy"])
        elif names:
            self.trending_up_var.set(names[0])

        if self.config.get("trending_down_strategy") in names:
            self.trending_down_var.set(self.config["trending_down_strategy"])
        elif names:
            self.trending_down_var.set(names[0])

        if self.config.get("ranging_strategy") in names:
            self.ranging_var.set(self.config["ranging_strategy"])
        elif names:
            self.ranging_var.set(names[0])

    # ------------------------------------------------------------------ #
    # OPTIMIZER WINDOWS (Phase C)
    # ------------------------------------------------------------------ #
    def open_single_optimizer_window(self) -> None:
        optimizer_envelope_single.open_window(self)

    def open_all_assets_optimizer_window(self) -> None:
        optimizer_envelope_all.open_window(self)

    def open_strategy_param_optimizer_window(self) -> None:
        optimizer_strategy_params.open_window(self)

    def open_fitness_scanner_window(self) -> None:
        """Open the Phase D Asset Fitness Tester window (non-modal)."""
        FitnessTabbedWindow(self)

    # UI TOGGLES
    # ------------------------------------------------------------------ #
    def _toggle_router_ui(self) -> None:
        if self.use_router_var.get():
            self.router_frame.grid()
            self.strategy_combo.configure(state="disabled")
            if self.run_mode_var.get() == "All Strategies":
                self.run_mode_var.set("Single")
            self.run_mode_combo["values"] = ["Single", "All Assets"]
        else:
            self.router_frame.grid_remove()
            self.strategy_combo.configure(state="readonly")
            self.run_mode_combo["values"] = ["Single", "All Strategies", "All Assets"]

    def _toggle_equity_area(self) -> None:
        if self.equity_var.get():
            self.equity_frame.grid()
        else:
            self.equity_frame.grid_remove()

    # Public wrappers for layout callbacks
    def toggle_router_ui(self) -> None:
        self._toggle_router_ui()

    def toggle_equity_area(self) -> None:
        self._toggle_equity_area()

    # ------------------------------------------------------------------ #
    # BACKTEST DISPATCH
    # ------------------------------------------------------------------ #
    def run_backtest(self) -> None:
        """
        Dispatch based on run_mode (Single / All Strategies / All Assets).
        """
        self.output_text.delete("1.0", tk.END)
        self.save_current_config()
        self.fig.clear()

        mode = self.mode_var.get()
        run_mode = self.run_mode_var.get()
        use_router = self.use_router_var.get()

        try:
            max_c = int(self.candles_var.get())
        except Exception:
            max_c = 0

        try:
            position_pct = float(self.position_pct_var.get())
            risk_pct = float(self.risk_pct_var.get())
            reward_rr = float(self.rr_var.get())
        except Exception:
            messagebox.showerror(
                "Error",
                "Invalid numeric settings for position_pct / risk_pct / reward_rr.",
            )
            return

        mappings: Optional[Dict[str, str]] = None
        if use_router:
            mappings = {
                "trending_up": self.trending_up_var.get(),
                "trending_down": self.trending_down_var.get(),
                "ranging": self.ranging_var.get(),
            }

        selection = self.file_var.get()
        if not selection:
            messagebox.showerror("No Data", "Select an asset/timeframe first.")
            return

        parts = selection.split()
        asset = parts[0]
        timeframe = parts[1] if len(parts) > 1 else self.timeframe_var.get()
        asset_file = f"{asset}_{timeframe}.csv"

        if run_mode == "Single":
            self._run_single(
                mode=mode,
                use_router=use_router,
                max_c=max_c,
                mappings=mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
        elif run_mode == "All Strategies":
            self._run_all_strategies(
                mode=mode,
                max_c=max_c,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
        elif run_mode == "All Assets":
            self._run_all_assets(
                mode=mode,
                use_router=use_router,
                max_c=max_c,
                mappings=mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
        else:
            messagebox.showerror("Error", f"Unknown run mode: {run_mode}")

    # ------------------------------------------------------------------ #
    # SINGLE BACKTEST HANDLER
    # ------------------------------------------------------------------ #
    def _run_single(
        self,
        mode: str,
        use_router: bool,
        max_c: int,
        mappings: Optional[Dict[str, str]],
        position_pct: float,
        risk_pct: float,
        reward_rr: float,
    ) -> None:
        sel = self.file_var.get()
        if not sel:
            messagebox.showerror("Error", "No data file selected")
            return

        parts = sel.split()
        asset = parts[0]
        timeframe = parts[1] if len(parts) > 1 else self.timeframe_var.get()
        asset_file = f"{asset}_{timeframe}.csv"

        strat = self.strategy_var.get()

        try:
            preamble, summary, result = run_single_backtest(
                asset_file=asset_file,
                strategy_name=strat,
                mode=mode,
                use_router=use_router,
                max_candles=max_c,
                strategy_mappings=mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )

            self.summary = summary

            self.output_text.insert(tk.END, preamble)
            self.output_text.insert(tk.END, self.summary)

            try:
                report = build_report(result)
                self.latest_report = report
                self.latest_report_label = (
                    f"{asset} | {strat} | {mode}{' (router)' if use_router else ''}"
                )
                self.report_available = True
                try:
                    self.reports_menu.entryconfig("Show Last Analytics", state="normal")
                except Exception:
                    pass
            except Exception:
                self.output_text.insert(
                    tk.END,
                    "\n[Reporting] Failed to build analytics report. See logs for details.\n",
                )

            if self.equity_var.get() and getattr(result, "trades", None):
                plot_equity_curve(self.fig, result.trades)
                self.canvas.draw()

            self.output_text.insert(tk.END, "\nBacktest completed.\n")
        except Exception:
            err = f"\nBACKTEST FAILED:\n{traceback.format_exc()}"
            self.output_text.insert(tk.END, err)
            messagebox.showerror("Backtest Failed", "Check output.")

    # ------------------------------------------------------------------ #
    # ALL STRATEGIES / ALL ASSETS
    # ------------------------------------------------------------------ #
    def _run_all_strategies(
        self,
        mode: str,
        max_c: int,
        position_pct: float,
        risk_pct: float,
        reward_rr: float,
    ) -> None:
        sel = self.file_var.get()
        if not sel:
            messagebox.showerror("Error", "No data file selected")
            return

        parts = sel.split()
        asset = parts[0]
        timeframe = parts[1] if len(parts) > 1 else self.timeframe_var.get()
        asset_file = f"{asset}_{timeframe}.csv"

        try:
            df_res, error_log = run_all_strategies_backtest(
                asset_file=asset_file,
                mode=mode,
                max_candles=max_c,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
            summary_text = format_all_strategies_summary(df_res)
            self.output_text.insert(tk.END, summary_text)
            if error_log:
                self.output_text.insert(tk.END, error_log)
        except Exception:
            err = f"\nALL-STRATEGIES BACKTEST FAILED:\n{traceback.format_exc()}"
            self.output_text.insert(tk.END, err)
            messagebox.showerror("Backtest Failed", "Backtest Failed")

    def _run_all_assets(
        self,
        mode: str,
        use_router: bool,
        max_c: int,
        mappings: Optional[Dict[str, str]],
        position_pct: float,
        risk_pct: float,
        reward_rr: float,
    ) -> None:
        tf = self.timeframe_var.get()
        strat = self.strategy_var.get()

        try:
            df_res, error_log = run_all_assets_backtest(
                timeframe=tf,
                strategy_name=strat,
                mode=mode,
                use_router=use_router,
                max_candles=max_c,
                strategy_mappings=mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
            summary_text = format_all_assets_summary(df_res)
            self.output_text.insert(tk.END, summary_text)
            if error_log:
                self.output_text.insert(tk.END, error_log)
        except Exception:
            err = f"\nALL-ASSETS BACKTEST FAILED:\n{traceback.format_exc()}"
            self.output_text.insert(tk.END, err)
            messagebox.showerror("Backtest Failed", "Backtest Failed")

    # ------------------------------------------------------------------ #
    # CLOSE HANDLER
    # ------------------------------------------------------------------ #
    def on_close(self) -> None:
        """Save current GUI state before exiting."""
        try:
            self.save_current_config()
        except Exception:
            # Don't block application exit on config save failures.
            pass
        self.root.destroy()

    # ------------------------------------------------------------------ #
    # COPY OUTPUT
    # ------------------------------------------------------------------ #
    def copy_output(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.summary)
        messagebox.showinfo("Copied", "Output copied!")

# gui/backtester_gui.py v3.2 (652 lines)