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
    RESULTS_DIR,
)
from core.backtest_runner import (
    run_single_backtest,
    run_all_strategies_backtest,
    run_all_assets_backtest,
)
from core.strategy_loader import load_strategies, list_strategies
from core.reporting import build_report
from core.optimizer import (
    grid_search_single_asset,
    grid_search_all_assets,
    grid_search_strategy_params_single_asset,
    select_good_region,
    summarize_region,
)
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

        self.menubar = menubar
        self.data_menu = data_menu
        self.reports_menu = reports_menu
        self.optimizer_menu = optimizer_menu

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
            for key, val in stats.items():
                lines.append(f"    {key}: {val}")

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
    # OPTIMIZER HELPERS
    # ------------------------------------------------------------------ #
    def _parse_float_list(self, text: str, fallback: float) -> List[float]:
        """
        Parse a comma-separated list of floats. If parsing fails or result is empty,
        return [fallback].
        """
        if not text:
            return [fallback]
        parts = [p.strip() for p in text.split(",") if p.strip()]
        vals: List[float] = []
        for p in parts:
            try:
                vals.append(float(p))
            except Exception:
                continue
        return vals or [fallback]

    def _parse_strategy_values(self, text: str) -> List[Any]:
        """
        Parse a comma-separated list of strategy parameter values.

        - Values containing '%' are kept as strings (e.g. "3%").
        - Others are parsed as float, then downcast to int if integral.
        - If parsing fails, keep as string.
        """
        if not text:
            return []
        vals: List[Any] = []
        for raw in text.split(","):
            v = raw.strip()
            if not v:
                continue
            if "%" in v:
                vals.append(v)
                continue
            try:
                f = float(v)
                if f.is_integer():
                    vals.append(int(f))
                else:
                    vals.append(f)
            except Exception:
                vals.append(v)
        return vals

    def _build_router_mappings(self) -> Dict[str, str]:
        """
        Build regime router mappings from the main GUI combo selections.
        """
        return {
            "trending_up": self.trending_up_var.get(),
            "trending_down": self.trending_down_var.get(),
            "ranging": self.ranging_var.get(),
        }

    def _get_available_timeframes(self) -> List[str]:
        """
        Return a sorted list of available timeframes from manifest.json.
        Fallback to ['1h'] if manifest can't be read or is missing.
        """
        if not os.path.exists(MANIFEST_FILE):
            return ["1h"]
        try:
            with open(MANIFEST_FILE, "r") as f:
                manifest = json.load(f)
        except Exception:
            return ["1h"]

        pairs = manifest.get("pairs", {})
        tfs = set()
        for _, tf_data in pairs.items():
            for tf in tf_data.keys():
                tfs.add(tf)
        return sorted(tfs) or ["1h"]

    @staticmethod
    def _parse_optional_float(text: str) -> Optional[float]:
        text = text.strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None

    @staticmethod
    def _parse_optional_int(text: str) -> Optional[int]:
        text = text.strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # OPTIMIZER WINDOWS – C1 (single asset) + C2 (all assets)
    # ------------------------------------------------------------------ #
    def open_single_optimizer_window(self) -> None:
        """
        Configure and run parameter optimization for a user-selected
        asset + strategy (engine envelope), with optional C4 filter.
        """
        # Default selections from main GUI
        default_asset_label = self.file_var.get()
        default_strategy = self.strategy_var.get()
        default_mode = self.mode_var.get()
        default_use_router = self.use_router_var.get()

        win = tk.Toplevel(self.root)
        win.title("Optimize Current Asset")
        win.configure(bg="#0d1117")

        # Top-row selectors: asset, strategy, mode, router toggle
        ttk.Label(win, text="Asset:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        asset_var = tk.StringVar(value=default_asset_label)
        asset_values = list(self.file_combo["values"])
        asset_combo = ttk.Combobox(win, textvariable=asset_var, values=asset_values, state="readonly", width=60)
        asset_combo.grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 2))

        ttk.Label(win, text="Strategy:").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        strat_var = tk.StringVar(value=default_strategy)
        strat_values = list(self.strategy_combo["values"])
        strat_combo = ttk.Combobox(win, textvariable=strat_var, values=strat_values, state="readonly", width=40)
        strat_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=2)

        ttk.Label(win, text="Mode:").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        mode_var = tk.StringVar(value=default_mode)
        mode_combo = ttk.Combobox(
            win,
            textvariable=mode_var,
            values=["conservative", "balanced", "aggressive"],
            state="readonly",
            width=20,
        )
        mode_combo.grid(row=2, column=1, sticky="w", padx=10, pady=2)

        use_router_var = tk.BooleanVar(value=default_use_router)
        ttk.Checkbutton(
            win,
            text="Use Regime Router (use current router mappings)",
            variable=use_router_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))

        # Param entries
        ttk.Label(win, text="position_pct values (comma-separated):").grid(
            row=4, column=0, sticky="w", padx=10, pady=(5, 2)
        )
        pos_default = f"{float(self.position_pct_var.get()):.1f}"
        pos_entry = ttk.Entry(win, width=40)
        pos_entry.insert(0, pos_default)
        pos_entry.grid(row=4, column=1, sticky="ew", padx=10, pady=(5, 2))

        ttk.Label(win, text="risk_pct values (comma-separated):").grid(
            row=5, column=0, sticky="w", padx=10, pady=(5, 2)
        )
        risk_default = f"{float(self.risk_pct_var.get()):.1f}"
        risk_entry = ttk.Entry(win, width=40)
        risk_entry.insert(0, risk_default)
        risk_entry.grid(row=5, column=1, sticky="ew", padx=10, pady=(5, 2))

        ttk.Label(win, text="reward_rr values (comma-separated):").grid(
            row=6, column=0, sticky="w", padx=10, pady=(5, 2)
        )
        rr_default = f"{float(self.rr_var.get()):.2f}"
        rr_entry = ttk.Entry(win, width=40)
        rr_entry.insert(0, rr_default)
        rr_entry.grid(row=6, column=1, sticky="ew", padx=10, pady=(5, 2))

        ttk.Label(win, text="Max candles (0 = all):").grid(
            row=7, column=0, sticky="w", padx=10, pady=(5, 10)
        )
        max_c_default = str(self.candles_var.get())
        max_c_entry = ttk.Entry(win, width=20)
        max_c_entry.insert(0, max_c_default)
        max_c_entry.grid(row=7, column=1, sticky="w", padx=10, pady=(5, 10))

        # Region filter (C4)
        filter_frame = ttk.LabelFrame(win, text="Region Filter (optional)", padding=8)
        filter_frame.grid(row=8, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))

        min_sharpe_var = tk.StringVar()
        max_dd_var = tk.StringVar()
        min_trades_var = tk.StringVar()
        min_return_var = tk.StringVar()
        top_n_var = tk.StringVar(value="50")
        apply_filter_var = tk.BooleanVar(value=True)

        ttk.Label(filter_frame, text="Min Sharpe:").grid(row=0, column=0, sticky="w")
        min_sharpe_entry = ttk.Entry(filter_frame, width=8, textvariable=min_sharpe_var)
        min_sharpe_entry.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(filter_frame, text="Max DD (%):").grid(row=0, column=2, sticky="w")
        max_dd_entry = ttk.Entry(filter_frame, width=8, textvariable=max_dd_var)
        max_dd_entry.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(filter_frame, text="Min Trades:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        min_trades_entry = ttk.Entry(filter_frame, width=8, textvariable=min_trades_var)
        min_trades_entry.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(filter_frame, text="Min Return (%):").grid(row=1, column=2, sticky="w", pady=(4, 0))
        min_return_entry = ttk.Entry(filter_frame, width=8, textvariable=min_return_var)
        min_return_entry.grid(row=1, column=3, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(filter_frame, text="Top N:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        top_n_entry = ttk.Entry(filter_frame, width=6, textvariable=top_n_var)
        top_n_entry.grid(row=2, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Checkbutton(
            filter_frame,
            text="Apply filter & show Top N",
            variable=apply_filter_var,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))

        # Status + Results
        status_label = ttk.Label(win, text="", foreground="#58a6ff")
        status_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))

        results_text = tk.Text(
            win,
            wrap="word",
            height=20,
            width=100,
            bg="#0d1117",
            fg="#c9d1d9",
        )
        results_text.grid(row=11, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="nsew")
        win.grid_rowconfigure(11, weight=1)
        win.grid_columnconfigure(1, weight=1)

        def run_optimize_single() -> None:
            try:
                sel_label = asset_var.get()
                if not sel_label:
                    messagebox.showerror("Optimizer", "No asset selected.")
                    return
                asset_file = sel_label.split(" (")[0]

                strat = strat_var.get()
                if not strat:
                    messagebox.showerror("Optimizer", "No strategy selected.")
                    return

                mode = mode_var.get()
                use_router = bool(use_router_var.get())

                pos_vals = self._parse_float_list(pos_entry.get(), float(self.position_pct_var.get()))
                risk_vals = self._parse_float_list(risk_entry.get(), float(self.risk_pct_var.get()))
                rr_vals = self._parse_float_list(rr_entry.get(), float(self.rr_var.get()))
                try:
                    max_c = int(max_c_entry.get())
                except Exception:
                    max_c = 0

                param_grid = {
                    "position_pct": pos_vals,
                    "risk_pct": risk_vals,
                    "reward_rr": rr_vals,
                }

                mappings = self._build_router_mappings() if use_router else None

                status_label.config(text="Running optimization...")
                win.config(cursor="watch")
                win.update_idletasks()

                df_res = grid_search_single_asset(
                    asset_file=asset_file,
                    strategy_name=strat,
                    mode=mode,
                    use_router=use_router,
                    param_grid=param_grid,
                    max_candles=max_c,
                    strategy_mappings=mappings,
                )

                results_text.delete("1.0", tk.END)

                if df_res.empty:
                    results_text.insert("1.0", "No valid optimization results.\n")
                    status_label.config(text="Optimization completed (0 valid combos).")
                else:
                    total = len(df_res)

                    df_show = df_res
                    filtered_count = total

                    if apply_filter_var.get():
                        min_sh = self._parse_optional_float(min_sharpe_var.get())
                        max_dd = self._parse_optional_float(max_dd_var.get())
                        min_tr = self._parse_optional_int(min_trades_var.get())
                        min_ret = self._parse_optional_float(min_return_var.get())

                        good = select_good_region(
                            df_res,
                            min_sharpe=min_sh,
                            max_dd_pct=max_dd,
                            min_trades=min_tr,
                            min_return_pct=min_ret,
                        )
                        filtered_count = len(good)

                        if filtered_count > 0:
                            try:
                                top_n = int(top_n_var.get())
                            except Exception:
                                top_n = 50
                            df_show = summarize_region(good, top_n=top_n)
                        else:
                            # If filter nukes everything, fall back to full table but report that.
                            try:
                                top_n = int(top_n_var.get())
                            except Exception:
                                top_n = 50
                            df_show = summarize_region(df_res, top_n=top_n)

                        status_label.config(
                            text=f"Optimization completed. Combos: {total}, passed filter: {filtered_count}."
                        )
                    else:
                        try:
                            top_n = int(top_n_var.get())
                        except Exception:
                            top_n = 50
                        df_show = summarize_region(df_res, top_n=top_n)
                        status_label.config(
                            text=f"Optimization completed. Combos: {total}."
                        )

                    results_text.insert("1.0", df_show.to_string(index=False) + "\n")

            except Exception:
                results_text.delete("1.0", tk.END)
                results_text.insert("1.0", "Optimization failed:\n\n" + traceback.format_exc())
                status_label.config(text="Optimization failed.")
            finally:
                win.config(cursor="")
                win.update_idletasks()

        ttk.Button(win, text="Run Optimization", command=run_optimize_single).grid(
            row=10, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="ew"
        )

    def open_all_assets_optimizer_window(self) -> None:
        """
        Configure and run parameter optimization across all assets
        for a chosen timeframe + strategy, with optional C4 filter.
        """
        default_tf = self.timeframe_var.get()
        default_strategy = self.strategy_var.get()
        default_mode = self.mode_var.get()
        default_use_router = self.use_router_var.get()

        win = tk.Toplevel(self.root)
        win.title("Optimize All Assets (timeframe)")
        win.configure(bg="#0d1117")

        # Timeframe, strategy, mode, router toggle
        ttk.Label(win, text="Timeframe:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        tf_values = self._get_available_timeframes()
        tf_var = tk.StringVar(value=default_tf if default_tf in tf_values else (tf_values[0] if tf_values else "1h"))
        tf_combo = ttk.Combobox(win, textvariable=tf_var, values=tf_values, state="readonly", width=20)
        tf_combo.grid(row=0, column=1, sticky="w", padx=10, pady=(10, 2))

        ttk.Label(win, text="Strategy:").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        strat_var = tk.StringVar(value=default_strategy)
        strat_values = list(self.strategy_combo["values"])
        strat_combo = ttk.Combobox(win, textvariable=strat_var, values=strat_values, state="readonly", width=40)
        strat_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=2)

        ttk.Label(win, text="Mode:").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        mode_var = tk.StringVar(value=default_mode)
        mode_combo = ttk.Combobox(
            win,
            textvariable=mode_var,
            values=["conservative", "balanced", "aggressive"],
            state="readonly",
            width=20,
        )
        mode_combo.grid(row=2, column=1, sticky="w", padx=10, pady=2)

        use_router_var = tk.BooleanVar(value=default_use_router)
        ttk.Checkbutton(
            win,
            text="Use Regime Router (use current router mappings)",
            variable=use_router_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))

        # Param entries
        ttk.Label(win, text="position_pct values (comma-separated):").grid(
            row=4, column=0, sticky="w", padx=10, pady=(5, 2)
        )
        pos_default = f"{float(self.position_pct_var.get()):.1f}"
        pos_entry = ttk.Entry(win, width=40)
        pos_entry.insert(0, pos_default)
        pos_entry.grid(row=4, column=1, sticky="ew", padx=10, pady=(5, 2))

        ttk.Label(win, text="risk_pct values (comma-separated):").grid(
            row=5, column=0, sticky="w", padx=10, pady=(5, 2)
        )
        risk_default = f"{float(self.risk_pct_var.get()):.1f}"
        risk_entry = ttk.Entry(win, width=40)
        risk_entry.insert(0, risk_default)
        risk_entry.grid(row=5, column=1, sticky="ew", padx=10, pady=(5, 2))

        ttk.Label(win, text="reward_rr values (comma-separated):").grid(
            row=6, column=0, sticky="w", padx=10, pady=(5, 2)
        )
        rr_default = f"{float(self.rr_var.get()):.2f}"
        rr_entry = ttk.Entry(win, width=40)
        rr_entry.insert(0, rr_default)
        rr_entry.grid(row=6, column=1, sticky="ew", padx=10, pady=(5, 2))

        ttk.Label(win, text="Max candles (0 = all):").grid(
            row=7, column=0, sticky="w", padx=10, pady=(5, 10)
        )
        max_c_default = str(self.candles_var.get())
        max_c_entry = ttk.Entry(win, width=20)
        max_c_entry.insert(0, max_c_default)
        max_c_entry.grid(row=7, column=1, sticky="w", padx=10, pady=(5, 10))

        # Region filter (C4)
        filter_frame = ttk.LabelFrame(win, text="Region Filter (optional)", padding=8)
        filter_frame.grid(row=8, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))

        min_sharpe_var = tk.StringVar()
        max_dd_var = tk.StringVar()
        min_trades_var = tk.StringVar()
        min_return_var = tk.StringVar()
        top_n_var = tk.StringVar(value="50")
        apply_filter_var = tk.BooleanVar(value=True)

        ttk.Label(filter_frame, text="Min Sharpe:").grid(row=0, column=0, sticky="w")
        min_sharpe_entry = ttk.Entry(filter_frame, width=8, textvariable=min_sharpe_var)
        min_sharpe_entry.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(filter_frame, text="Max DD (%):").grid(row=0, column=2, sticky="w")
        max_dd_entry = ttk.Entry(filter_frame, width=8, textvariable=max_dd_var)
        max_dd_entry.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(filter_frame, text="Min Trades:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        min_trades_entry = ttk.Entry(filter_frame, width=8, textvariable=min_trades_var)
        min_trades_entry.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(filter_frame, text="Min Return (%):").grid(row=1, column=2, sticky="w", pady=(4, 0))
        min_return_entry = ttk.Entry(filter_frame, width=8, textvariable=min_return_var)
        min_return_entry.grid(row=1, column=3, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(filter_frame, text="Top N:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        top_n_entry = ttk.Entry(filter_frame, width=6, textvariable=top_n_var)
        top_n_entry.grid(row=2, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Checkbutton(
            filter_frame,
            text="Apply filter & show Top N",
            variable=apply_filter_var,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))

        # Status + results
        status_label = ttk.Label(win, text="", foreground="#58a6ff")
        status_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))

        results_text = tk.Text(
            win,
            wrap="word",
            height=20,
            width=100,
            bg="#0d1117",
            fg="#c9d1d9",
        )
        results_text.grid(row=11, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="nsew")
        win.grid_rowconfigure(11, weight=1)
        win.grid_columnconfigure(1, weight=1)

        def run_optimize_all_assets() -> None:
            try:
                tf = tf_var.get()
                strat = strat_var.get()
                mode = mode_var.get()
                use_router = bool(use_router_var.get())

                if not strat:
                    messagebox.showerror("Optimizer", "No strategy selected.")
                    return

                pos_vals = self._parse_float_list(pos_entry.get(), float(self.position_pct_var.get()))
                risk_vals = self._parse_float_list(risk_entry.get(), float(self.risk_pct_var.get()))
                rr_vals = self._parse_float_list(rr_entry.get(), float(self.rr_var.get()))
                try:
                    max_c = int(max_c_entry.get())
                except Exception:
                    max_c = 0

                param_grid = {
                    "position_pct": pos_vals,
                    "risk_pct": risk_vals,
                    "reward_rr": rr_vals,
                }

                mappings = self._build_router_mappings() if use_router else None

                status_label.config(text="Running asset sweep...")
                win.config(cursor="watch")
                win.update_idletasks()

                df_res = grid_search_all_assets(
                    timeframe=tf,
                    strategy_name=strat,
                    mode=mode,
                    use_router=use_router,
                    param_grid=param_grid,
                    max_candles=max_c,
                    strategy_mappings=mappings,
                )

                results_text.delete("1.0", tk.END)

                if df_res.empty:
                    results_text.insert("1.0", "No valid optimization results.\n")
                    status_label.config(text="Asset sweep completed (0 valid assets).")
                else:
                    total = len(df_res)

                    df_show = df_res
                    filtered_count = total

                    if apply_filter_var.get():
                        min_sh = self._parse_optional_float(min_sharpe_var.get())
                        max_dd = self._parse_optional_float(max_dd_var.get())
                        min_tr = self._parse_optional_int(min_trades_var.get())
                        min_ret = self._parse_optional_float(min_return_var.get())

                        good = select_good_region(
                            df_res,
                            min_sharpe=min_sh,
                            max_dd_pct=max_dd,
                            min_trades=min_tr,
                            min_return_pct=min_ret,
                        )
                        filtered_count = len(good)

                        if filtered_count > 0:
                            try:
                                top_n = int(top_n_var.get())
                            except Exception:
                                top_n = 50
                            df_show = summarize_region(good, top_n=top_n)
                        else:
                            try:
                                top_n = int(top_n_var.get())
                            except Exception:
                                top_n = 50
                            df_show = summarize_region(df_res, top_n=top_n)

                        status_label.config(
                            text=f"Asset sweep completed. Assets: {total}, passed filter: {filtered_count}."
                        )
                    else:
                        try:
                            top_n = int(top_n_var.get())
                        except Exception:
                            top_n = 50
                        df_show = summarize_region(df_res, top_n=top_n)
                        status_label.config(
                            text=f"Asset sweep completed. Assets: {total}."
                        )

                    results_text.insert("1.0", df_show.to_string(index=False) + "\n")

            except Exception:
                results_text.delete("1.0", tk.END)
                results_text.insert("1.0", "Asset sweep failed:\n\n" + traceback.format_exc())
                status_label.config(text="Asset sweep failed.")
            finally:
                win.config(cursor="")
                win.update_idletasks()

        ttk.Button(win, text="Run Asset Sweep", command=run_optimize_all_assets).grid(
            row=10, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="ew"
        )

    # ------------------------------------------------------------------ #
    # OPTIMIZER WINDOW – C3 (strategy params, single asset)
    # ------------------------------------------------------------------ #
    def open_strategy_param_optimizer_window(self) -> None:
        """
        Configure and run strategy-level parameter optimization (C3)
        for a single asset + strategy.

        Notes:
        - Always runs in NON-router mode (tests the selected strategy directly).
        - Engine risk envelope is fixed (single position_pct / risk_pct / RR).
        - User specifies up to 3 dotted param paths + comma-separated values.
        """
        default_asset_label = self.file_var.get()
        default_strategy = self.strategy_var.get()
        default_mode = self.mode_var.get()

        win = tk.Toplevel(self.root)
        win.title("Optimize Strategy Params (single asset)")
        win.configure(bg="#0d1117")

        # Asset / strategy / mode
        ttk.Label(win, text="Asset:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        asset_var = tk.StringVar(value=default_asset_label)
        asset_values = list(self.file_combo["values"])
        asset_combo = ttk.Combobox(win, textvariable=asset_var, values=asset_values, state="readonly", width=60)
        asset_combo.grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 2))

        ttk.Label(win, text="Strategy:").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        strat_var = tk.StringVar(value=default_strategy)
        strat_values = list(self.strategy_combo["values"])
        strat_combo = ttk.Combobox(win, textvariable=strat_var, values=strat_values, state="readonly", width=40)
        strat_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=2)

        ttk.Label(win, text="Mode:").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        mode_var = tk.StringVar(value=default_mode)
        mode_combo = ttk.Combobox(
            win,
            textvariable=mode_var,
            values=["conservative", "balanced", "aggressive"],
            state="readonly",
            width=20,
        )
        mode_combo.grid(row=2, column=1, sticky="w", padx=10, pady=2)

        # Engine envelope – fixed values
        ttk.Label(win, text="Position size % (fixed):").grid(row=3, column=0, sticky="w", padx=10, pady=(8, 2))
        pos_val_var = tk.StringVar(value=f"{float(self.position_pct_var.get()):.1f}")
        pos_entry = ttk.Entry(win, width=12, textvariable=pos_val_var)
        pos_entry.grid(row=3, column=1, sticky="w", padx=10, pady=(8, 2))

        ttk.Label(win, text="Risk per trade % (fixed):").grid(row=4, column=0, sticky="w", padx=10, pady=2)
        risk_val_var = tk.StringVar(value=f"{float(self.risk_pct_var.get()):.1f}")
        risk_entry = ttk.Entry(win, width=12, textvariable=risk_val_var)
        risk_entry.grid(row=4, column=1, sticky="w", padx=10, pady=2)

        ttk.Label(win, text="Reward:Risk (fixed):").grid(row=5, column=0, sticky="w", padx=10, pady=2)
        rr_val_var = tk.StringVar(value=f"{float(self.rr_var.get()):.2f}")
        rr_entry = ttk.Entry(win, width=12, textvariable=rr_val_var)
        rr_entry.grid(row=5, column=1, sticky="w", padx=10, pady=2)

        ttk.Label(win, text="Max candles (0 = all):").grid(row=6, column=0, sticky="w", padx=10, pady=(5, 10))
        max_c_default = str(self.candles_var.get())
        max_c_entry = ttk.Entry(win, width=12)
        max_c_entry.insert(0, max_c_default)
        max_c_entry.grid(row=6, column=1, sticky="w", padx=10, pady=(5, 10))

        # Strategy param grid (up to 3 paths)
        param_frame = ttk.LabelFrame(win, text="Strategy Parameter Grid", padding=8)
        param_frame.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))

        ttk.Label(param_frame, text="Param path #1:").grid(row=0, column=0, sticky="w")
        p1_path_var = tk.StringVar(value="entry.conditions[1].below")
        p1_path_entry = ttk.Entry(param_frame, width=30, textvariable=p1_path_var)
        p1_path_entry.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(param_frame, text="Values:").grid(row=0, column=2, sticky="w")
        p1_vals_var = tk.StringVar(value="25, 30, 35, 40")
        p1_vals_entry = ttk.Entry(param_frame, width=30, textvariable=p1_vals_var)
        p1_vals_entry.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(param_frame, text="Param path #2:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        p2_path_var = tk.StringVar(value="exit.stop_loss")
        p2_path_entry = ttk.Entry(param_frame, width=30, textvariable=p2_path_var)
        p2_path_entry.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(param_frame, text="Values:").grid(row=1, column=2, sticky="w", pady=(4, 0))
        p2_vals_var = tk.StringVar(value="2%, 3%, 4%")
        p2_vals_entry = ttk.Entry(param_frame, width=30, textvariable=p2_vals_var)
        p2_vals_entry.grid(row=1, column=3, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(param_frame, text="Param path #3:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        p3_path_var = tk.StringVar(value="exit.take_profit")
        p3_path_entry = ttk.Entry(param_frame, width=30, textvariable=p3_path_var)
        p3_path_entry.grid(row=2, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(param_frame, text="Values:").grid(row=2, column=2, sticky="w", pady=(4, 0))
        p3_vals_var = tk.StringVar(value="8%, 9%, 12%")
        p3_vals_entry = ttk.Entry(param_frame, width=30, textvariable=p3_vals_var)
        p3_vals_entry.grid(row=2, column=3, sticky="w", padx=4, pady=(4, 0))

        # Region filter (C4)
        filter_frame = ttk.LabelFrame(win, text="Region Filter (optional)", padding=8)
        filter_frame.grid(row=8, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))

        min_sharpe_var = tk.StringVar()
        max_dd_var = tk.StringVar()
        min_trades_var = tk.StringVar()
        min_return_var = tk.StringVar()
        top_n_var = tk.StringVar(value="50")
        apply_filter_var = tk.BooleanVar(value=True)

        ttk.Label(filter_frame, text="Min Sharpe:").grid(row=0, column=0, sticky="w")
        min_sharpe_entry = ttk.Entry(filter_frame, width=8, textvariable=min_sharpe_var)
        min_sharpe_entry.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(filter_frame, text="Max DD (%):").grid(row=0, column=2, sticky="w")
        max_dd_entry = ttk.Entry(filter_frame, width=8, textvariable=max_dd_var)
        max_dd_entry.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(filter_frame, text="Min Trades:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        min_trades_entry = ttk.Entry(filter_frame, width=8, textvariable=min_trades_var)
        min_trades_entry.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(filter_frame, text="Min Return (%):").grid(row=1, column=2, sticky="w", pady=(4, 0))
        min_return_entry = ttk.Entry(filter_frame, width=8, textvariable=min_return_var)
        min_return_entry.grid(row=1, column=3, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(filter_frame, text="Top N:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        top_n_entry = ttk.Entry(filter_frame, width=6, textvariable=top_n_var)
        top_n_entry.grid(row=2, column=1, sticky="w", padx=4, pady=(4, 0))

        ttk.Checkbutton(
            filter_frame,
            text="Apply filter & show Top N",
            variable=apply_filter_var,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))

        # Info + status + results
        info_label = ttk.Label(
            win,
            text="Note: Strategy optimizer always runs in NON-router mode\n"
                 "(it tests the selected strategy directly).",
            foreground="#8b949e",
        )
        info_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))

        status_label = ttk.Label(win, text="", foreground="#58a6ff")
        status_label.grid(row=10, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))

        results_text = tk.Text(
            win,
            wrap="word",
            height=20,
            width=100,
            bg="#0d1117",
            fg="#c9d1d9",
        )
        results_text.grid(row=12, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="nsew")
        win.grid_rowconfigure(12, weight=1)
        win.grid_columnconfigure(1, weight=1)

        def run_strategy_opt() -> None:
            try:
                sel_label = asset_var.get()
                if not sel_label:
                    messagebox.showerror("Strategy Optimizer", "No asset selected.")
                    return
                asset_file = sel_label.split(" (")[0]

                strat = strat_var.get()
                if not strat:
                    messagebox.showerror("Strategy Optimizer", "No strategy selected.")
                    return

                mode = mode_var.get()

                # Engine envelope
                try:
                    pos_val = float(pos_val_var.get())
                except Exception:
                    pos_val = float(self.position_pct_var.get())
                try:
                    risk_val = float(risk_val_var.get())
                except Exception:
                    risk_val = float(self.risk_pct_var.get())
                try:
                    rr_val = float(rr_val_var.get())
                except Exception:
                    rr_val = float(self.rr_var.get())
                try:
                    max_c = int(max_c_entry.get())
                except Exception:
                    max_c = 0

                # Build strategy_param_grid from up to 3 paths
                strategy_param_grid: Dict[str, List[Any]] = {}
                for path_var, vals_var in [
                    (p1_path_var, p1_vals_var),
                    (p2_path_var, p2_vals_var),
                    (p3_path_var, p3_vals_var),
                ]:
                    path = path_var.get().strip()
                    if not path:
                        continue
                    vals = self._parse_strategy_values(vals_var.get())
                    if vals:
                        strategy_param_grid[path] = vals

                if not strategy_param_grid:
                    messagebox.showerror(
                        "Strategy Optimizer",
                        "No strategy parameter paths/values defined.\n"
                        "Specify at least one param path and values.",
                    )
                    return

                status_label.config(text="Running strategy param optimization...")
                win.config(cursor="watch")
                win.update_idletasks()

                df_res = grid_search_strategy_params_single_asset(
                    asset_file=asset_file,
                    strategy_name=strat,
                    mode=mode,
                    strategy_param_grid=strategy_param_grid,
                    position_pct=pos_val,
                    risk_pct=risk_val,
                    reward_rr=rr_val,
                    max_candles=max_c,
                )

                results_text.delete("1.0", tk.END)

                if df_res.empty:
                    results_text.insert("1.0", "No valid optimization results (empty table).\n")
                    status_label.config(text="Strategy optimization completed (0 combos).")
                else:
                    total = len(df_res)
                    df_show = df_res
                    filtered_count = total

                    if apply_filter_var.get():
                        min_sh = self._parse_optional_float(min_sharpe_var.get())
                        max_dd = self._parse_optional_float(max_dd_var.get())
                        min_tr = self._parse_optional_int(min_trades_var.get())
                        min_ret = self._parse_optional_float(min_return_var.get())

                        good = select_good_region(
                            df_res,
                            min_sharpe=min_sh,
                            max_dd_pct=max_dd,
                            min_trades=min_tr,
                            min_return_pct=min_ret,
                        )
                        filtered_count = len(good)

                        if filtered_count > 0:
                            try:
                                top_n = int(top_n_var.get())
                            except Exception:
                                top_n = 50
                            df_show = summarize_region(good, top_n=top_n)
                        else:
                            try:
                                top_n = int(top_n_var.get())
                            except Exception:
                                top_n = 50
                            df_show = summarize_region(df_res, top_n=top_n)

                        status_label.config(
                            text=f"Strategy optimization completed. Combos: {total}, passed filter: {filtered_count}."
                        )
                    else:
                        try:
                            top_n = int(top_n_var.get())
                        except Exception:
                            top_n = 50
                        df_show = summarize_region(df_res, top_n=top_n)
                        status_label.config(
                            text=f"Strategy optimization completed. Combos: {total}."
                        )

                    results_text.insert("1.0", df_show.to_string(index=False) + "\n")

            except Exception:
                results_text.delete("1.0", tk.END)
                results_text.insert("1.0", "Strategy optimization failed:\n\n" + traceback.format_exc())
                status_label.config(text="Strategy optimization failed.")
            finally:
                win.config(cursor="")
                win.update_idletasks()

        ttk.Button(win, text="Run Strategy Optimization", command=run_strategy_opt).grid(
            row=11, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="ew"
        )

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
            messagebox.showerror("Backtest Failed", "Backtest Failed")

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
            messagebox.showerror("Backtest Failed", "Backtest Failed")

    # ------------------------------------------------------------------ #
    # COPY OUTPUT
    # ------------------------------------------------------------------ #
    def copy_output(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.summary)
        messagebox.showinfo("Copied", "Output copied!")


# gui/backtester_gui.py v2.4 (1421 lines)
