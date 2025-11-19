# gui/backtester_gui.py
# Purpose: Define BacktesterGUI and connect UI elements to core backtest logic.
# Major External Functions/Classes: BacktesterGUI
# Notes: Layout and styles live in gui/layout.py and gui/styles.py respectively.

import json
import os
import sys
import traceback
from typing import Any, Dict, Optional

import tkinter as tk
from tkinter import ttk, messagebox

from core.config_manager import (
    load_config,
    save_config,
    MANIFEST_FILE,
    RESULTS_DIR,
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
from gui.results_display import (
    plot_equity_curve,
    format_all_strategies_summary,
    format_all_assets_summary,
)


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

        self.df = None
        self.trades = []
        self.summary: str = ""
        self.latest_report: Dict[str, Any] = {}
        self.latest_report_label: str = ""
        self.report_available: bool = False

        self.config: Dict[str, Any] = load_config()

        setup_styles()
        self.create_menu()
        create_left_panel(self)
        create_right_panel(self)

        # Strategies, data, and UI initial state
        self.load_strategies()
        self.scan_data_files()
        self.toggle_router_ui()
        self.toggle_equity_area()

    # ------------------------------------------------------------------ #
    # CONFIG
    # ------------------------------------------------------------------ #
    def _build_config_dict(self) -> Dict[str, Any]:
        return {
            "data_file": self.file_var.get(),
            "timeframe": self.timeframe_var.get(),
            "strategy": self.strategy_var.get(),
            "mode": self.mode_var.get(),
            "candles": self.candles_var.get(),
            "show_equity": self.equity_var.get(),
            "run_mode": self.run_mode_var.get(),
            "use_router": self.use_router_var.get(),
            "trending_up_strategy": self.trending_up_var.get(),
            "trending_down_strategy": self.trending_down_var.get(),
            "ranging_strategy": self.ranging_var.get(),
            "position_pct": self.position_pct_var.get(),
            "risk_pct": self.risk_pct_var.get(),
            "reward_rr": self.rr_var.get(),
        }

    def save_current_config(self) -> None:
        cfg = self._build_config_dict()
        save_config(cfg)

    # ------------------------------------------------------------------ #
    # MENU
    # ------------------------------------------------------------------ #
    def create_menu(self) -> None:
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
        reports_menu.add_command(
            label="Open Results Folder",
            command=self.open_results_folder,
        )

        self.menubar = menubar
        self.data_menu = data_menu
        self.reports_menu = reports_menu

    # ------------------------------------------------------------------ #
    # REPORTS
    # ------------------------------------------------------------------ #
    def show_last_analytics(self) -> None:
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
            height=25,
            width=100,
            bg="#0d1117",
            fg="#c9d1d9",
        )
        text.pack(fill="both", expand=True, padx=10, pady=10)

        report = self.latest_report
        meta = report.get("meta", {})
        risk = report.get("risk", {})
        streaks = report.get("streaks", {})
        drawdown = report.get("drawdown", {})
        regimes = report.get("regimes", {})

        lines = []
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
            for k, v in stats.items():
                lines.append(f"    {k}: {v}")

        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    def open_results_folder(self) -> None:
        path = RESULTS_DIR
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception as e:
            messagebox.showerror(
                "Error", f"Could not open results folder:\n{path}\n\n{e}"
            )

    # ------------------------------------------------------------------ #
    # UI TOGGLES
    # ------------------------------------------------------------------ #
    def toggle_router_ui(self) -> None:
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

    def toggle_equity_area(self) -> None:
        """
        Show/hide the equity curve (matplotlib canvas) based on equity_var.
        """
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return

        widget = canvas.get_tk_widget()
        if self.equity_var.get():
            widget.grid()
        else:
            widget.grid_remove()

    # ------------------------------------------------------------------ #
    # DATA + STRATEGIES
    # ------------------------------------------------------------------ #
    def scan_data_files(self) -> None:
        """
        Populate the data file dropdown based on manifest.json.
        """
        self.file_combo["values"] = []
        self.file_var.set("")

        if not os.path.exists(MANIFEST_FILE):
            return

        try:
            with open(MANIFEST_FILE, "r") as f:
                manifest = json.load(f)
        except Exception:
            return

        pairs = manifest.get("pairs", {})
        entries = []
        for pair, tf_data in pairs.items():
            for tf, meta in tf_data.items():
                fname = meta.get("file")
                candles = meta.get("candles", "")
                label = f"{fname} ({pair} {tf}, {candles} candles)"
                entries.append(label)

        entries.sort()
        self.file_combo["values"] = entries

        if entries:
            last = self.config.get("data_file", "")
            match = [e for e in entries if e.startswith(last)] if last else []
            self.file_var.set(match[0] if match else entries[0])

    def load_strategies(self) -> None:
        """
        Populate strategy comboboxes from the strategies/ directory.
        """
        load_strategies()
        names = sorted(list_strategies())
        self.strategy_combo["values"] = names
        self.trending_up_combo["values"] = names
        self.trending_down_combo["values"] = names
        self.ranging_combo["values"] = names

        if names:
            if self.config.get("strategy") in names:
                self.strategy_var.set(self.config["strategy"])
            else:
                self.strategy_var.set(names[0])

            if self.config.get("trending_up_strategy") in names:
                self.trending_up_var.set(self.config["trending_up_strategy"])
            else:
                self.trending_up_var.set(names[0])

            if self.config.get("trending_down_strategy") in names:
                self.trending_down_var.set(self.config["trending_down_strategy"])
            else:
                self.trending_down_var.set(names[0])

            if self.config.get("ranging_strategy") in names:
                self.ranging_var.set(self.config["ranging_strategy"])
            else:
                self.ranging_var.set(names[0])

    # ------------------------------------------------------------------ #
    # RUN DISPATCH
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

        position_pct = float(self.position_pct_var.get())
        risk_pct = float(self.risk_pct_var.get())
        reward_rr = float(self.rr_var.get())

        mappings: Optional[Dict[str, str]] = None
        if use_router:
            mappings = {
                "trending_up": self.trending_up_var.get(),
                "trending_down": self.trending_down_var.get(),
                "ranging": self.ranging_var.get(),
            }

        if run_mode == "Single":
            self._run_single(
                mode,
                use_router,
                max_c,
                mappings,
                position_pct,
                risk_pct,
                reward_rr,
            )
        elif run_mode == "All Strategies":
            self._run_all_strategies(
                mode,
                max_c,
                position_pct,
                risk_pct,
                reward_rr,
            )
        elif run_mode == "All Assets":
            self._run_all_assets(
                mode,
                use_router,
                max_c,
                mappings,
                position_pct,
                risk_pct,
                reward_rr,
            )

    # ------------------------------------------------------------------ #
    # SINGLE RUN
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
        asset = sel.split(" (")[0]
        strat = self.strategy_var.get()

        try:
            preamble, summary, result = run_single_backtest(
                asset_file=asset,
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

            # Phase B: build and store advanced analytics for GUI
            try:
                report = build_report(result)
                self.latest_report = report
                self.latest_report_label = (
                    f"{asset} | {strat} | {mode}"
                    f"{' (router)' if use_router else ''}"
                )
                self.report_available = True

                if hasattr(self, "reports_menu"):
                    self.reports_menu.entryconfig(0, state="normal")

                risk = report.get("risk", {})
                streaks = report.get("streaks", {})

                adv_lines = [
                    "\n=== ADVANCED ANALYTICS ===",
                    f"Expectancy (R):         {risk.get('expectancy_R', 0): .3f}",
                    f"Avg Win R / Avg Loss R: {risk.get('avg_R_win', 0): .3f} / {risk.get('avg_R_loss', 0): .3f}",
                    f"Mean Return / Vol (%):  {risk.get('mean_return_pct', 0): .3f} / {risk.get('volatility_pct', 0): .3f}",
                    f"Sortino:                {risk.get('sortino', 0): .3f}",
                    f"MAR:                    {risk.get('mar', 0): .3f}",
                    f"Longest Win Streak:     {streaks.get('longest_win_streak', 0)}",
                    f"Longest Loss Streak:    {streaks.get('longest_loss_streak', 0)}",
                    "",
                ]
                self.output_text.insert(tk.END, "\n".join(adv_lines))
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
    # ALL STRATEGIES
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
        asset = sel.split(" (")[0]

        try:
            df_res, error_log = run_all_strategies_backtest(
                asset_file=asset,
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
            messagebox.showerror("Backtest Failed", "Check output.")

    # ------------------------------------------------------------------ #
    # ALL ASSETS
    # ------------------------------------------------------------------ #
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
            messagebox.showerror("Backtest Failed", "Check output.")

    # ------------------------------------------------------------------ #
    # COPY OUTPUT
    # ------------------------------------------------------------------ #
    def copy_output(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.summary)
        messagebox.showinfo("Copied", "Output copied!")


# gui/backtester_gui.py v2.0 (517 lines)
