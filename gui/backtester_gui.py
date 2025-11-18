# gui/backtester_gui.py
# Purpose: Define BacktesterGUI and connect UI elements to core backtest logic.
# Major External Functions/Classes: BacktesterGUI
# Notes: Layout and styles live in gui/layout.py and gui/styles.py respectively.

import json
import os
import traceback
from typing import Any, Dict, Optional

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
        self.root.state("zoomed")
        self.root.configure(bg="#0d1117")

        self.df = None
        self.trades = []
        self.summary = ""
        self.config: Dict[str, Any] = load_config()

        setup_styles()
        self.create_menu()
        create_left_panel(self)
        create_right_panel(self)

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

    def save_config(self) -> None:
        cfg = self._build_config_dict()
        save_config(cfg)

    # ------------------------------------------------------------------ #
    # MENU
    # ------------------------------------------------------------------ #
    def create_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        data_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Data", menu=data_menu)
        data_menu.add_command(label="Rescan Data", command=self.scan_data_files)

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
        self.save_config()

    def toggle_equity_area(self) -> None:
        if self.equity_var.get():
            self.canvas.get_tk_widget().grid()
        else:
            self.canvas.get_tk_widget().grid_remove()
        self.save_config()

    # ------------------------------------------------------------------ #
    # DATA / STRATEGY LOADING
    # ------------------------------------------------------------------ #
    def scan_data_files(self) -> None:
        if not os.path.exists(MANIFEST_FILE):
            return

        try:
            with open(MANIFEST_FILE, "r") as f:
                manifest = json.load(f)
        except Exception:
            return

        tf = self.timeframe_var.get()
        items = []
        for pair, data in manifest.get("pairs", {}).items():
            if tf in data:
                items.append((data[tf]["file"], data[tf]["candles"]))

        self.file_combo["values"] = [f"{f[0]} ({f[1]} candles)" for f in items]
        if items and not self.file_var.get():
            self.file_combo.current(0)
            self.file_var.set(items[0][0])

    def load_strategies(self) -> None:
        load_strategies()
        strat_list = list_strategies()
        for combo in (
            self.strategy_combo,
            self.trending_up_combo,
            self.trending_down_combo,
            self.ranging_combo,
        ):
            combo["values"] = strat_list
        if strat_list:
            self.strategy_combo.set(self.config.get("strategy", strat_list[0]))
            self.trending_up_combo.set(
                self.config.get("trending_up_strategy", strat_list[0])
            )
            self.trending_down_combo.set(
                self.config.get("trending_down_strategy", strat_list[0])
            )
            self.ranging_combo.set(
                self.config.get("ranging_strategy", strat_list[0])
            )

    # ------------------------------------------------------------------ #
    # RUN LOGIC
    # ------------------------------------------------------------------ #
    def run_backtest(self) -> None:
        self.save_config()
        self.output_text.delete(1.0, tk.END)
        self.fig.clear()

        run_mode = self.run_mode_var.get()
        use_router = self.use_router_var.get()
        mode = self.mode_var.get()
        tf = self.timeframe_var.get()
        max_c = int(self.candles_var.get() or 0)

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
                tf,
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

            if self.equity_var.get() and result.trades:
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
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run all strategies:\n{e}")
            return

        if error_log:
            self.output_text.insert(tk.END, error_log)

        summary_text = format_all_strategies_summary(df_res)
        self.output_text.insert(tk.END, summary_text)

    # ------------------------------------------------------------------ #
    # ALL ASSETS
    # ------------------------------------------------------------------ #
    def _run_all_assets(
        self,
        mode: str,
        use_router: bool,
        max_c: int,
        tf: str,
        mappings: Optional[Dict[str, str]],
        position_pct: float,
        risk_pct: float,
        reward_rr: float,
    ) -> None:
        strat = self.strategy_var.get()
        if not strat:
            messagebox.showerror("Error", "No strategy selected")
            return

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
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run all assets:\n{e}")
            return

        if error_log:
            self.output_text.insert(tk.END, error_log)

        summary_text = format_all_assets_summary(df_res)
        self.output_text.insert(tk.END, summary_text)

    # ------------------------------------------------------------------ #
    # COPY OUTPUT
    # ------------------------------------------------------------------ #
    def copy_output(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.summary)
        messagebox.showinfo("Copied", "Output copied!")


# gui/backtester_gui.py v1.1 (349 lines)
