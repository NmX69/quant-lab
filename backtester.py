# backtester.py

import os
import sys
import json
import pandas as pd
import traceback
import re
from typing import Any, List, Tuple, Dict
from decimal import Decimal
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.indicators import add_indicators_and_regime
from core.engine import run_backtest
from core.strategy_loader import load_strategies, list_strategies
from core.results import BacktestResult

CONFIG_FILE = os.path.join(PROJECT_ROOT, "backtester_config.json")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MANIFEST_FILE = os.path.join(DATA_DIR, "manifest.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")


class BacktesterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Regime-Aware Backtester")
        self.root.geometry("1700x1000")
        self.root.state('zoomed')
        self.root.configure(bg="#0d1117")

        self.df = None
        self.trades = []
        self.summary = ""
        self.config = self.load_config()

        self.setup_styles()
        self.create_menu()
        self.create_widgets()
        self.load_strategies()
        self.scan_data_files()
        self.toggle_router_ui()
        self.toggle_equity_area()

    # ------------------------------------------------------------------ #
    # CONFIG
    # ------------------------------------------------------------------ #
    def load_config(self):
        default = {
            "data_file": "",
            "timeframe": "1h",
            "strategy": "",
            "mode": "balanced",
            "candles": 0,
            "show_equity": True,
            "run_mode": "Single",
            "use_router": False,
            "trending_up_strategy": "trend_macd",
            "trending_down_strategy": "trend_macd",
            "ranging_strategy": "range_rsi_bb",
            # Risk / sizing defaults (GUI sliders)
            "position_pct": 15.0,   # % of equity used as notional per trade
            "risk_pct": 1.0,        # % of equity risked per trade
            "reward_rr": 1.5,       # reward:risk multiple
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                default.update(loaded)
            except:
                pass
        return default

    def save_config(self):
        cfg = {
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
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except:
            pass

    # ------------------------------------------------------------------ #
    # STYLES
    # ------------------------------------------------------------------ #
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background='#0d1117', foreground='#c9d1d9',
                        font=('Consolas', 16))
        style.configure('TLabel', background='#0d1117', foreground='#58a6ff',
                        font=('Consolas', 16, 'bold'))
        style.configure('TButton', padding=8, font=('Consolas', 16, 'bold'))
        style.map('TButton', background=[('active', '#238636')],
                  foreground=[('active', 'white')])
        style.configure('TCombobox', fieldbackground='white',
                        background='white', foreground='black',
                        font=('Consolas', 16))
        style.map('TCombobox', fieldbackground=[('readonly', 'white')])
        style.configure('TEntry', fieldbackground='white',
                        background='white', foreground='black',
                        font=('Consolas', 16))
        style.configure('TCheckbutton', background='#0d1117',
                        foreground='#c9d1d9', font=('Consolas', 16))

    # ------------------------------------------------------------------ #
    # MENU
    # ------------------------------------------------------------------ #
    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        data_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Data", menu=data_menu)
        data_menu.add_command(label="Rescan Data", command=self.scan_data_files)

    # ------------------------------------------------------------------ #
    # HEADER
    # ------------------------------------------------------------------ #
    def _make_header(self, asset: str, strat: str, use_router: bool) -> str:
        asset_sym = asset.split("_")[0]
        if use_router:
            return f"BACKTEST (router) – {asset_sym}"
        else:
            return f"BACKTEST: {strat} – {asset_sym}"

    # ------------------------------------------------------------------ #
    # WIDGETS
    # ------------------------------------------------------------------ #
    def create_widgets(self):
        # LEFT SIDE: core controls only (shorter so RUN button stays on-screen)
        left = ttk.Frame(self.root, padding="20")
        left.grid(row=0, column=0, sticky="ns", padx=20, pady=20)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        ttk.Label(left, text="REGIME BACKTESTER",
                  font=('Consolas', 20, 'bold'), foreground='#58a6ff') \
            .grid(row=0, column=0, columnspan=3, pady=(0, 20))

        ttk.Label(left, text="TIMEFRAME").grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.timeframe_var = tk.StringVar(value=self.config.get("timeframe", "1h"))
        ttk.Combobox(left, textvariable=self.timeframe_var,
                     values=["1h"], state="readonly") \
            .grid(row=1, column=1, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(left, text="DATA FILE").grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.file_var = tk.StringVar(value=self.config.get("data_file", ""))
        self.file_combo = ttk.Combobox(left, textvariable=self.file_var,
                                       state="readonly")
        self.file_combo.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(left, text="STRATEGY").grid(row=3, column=0, sticky="w", pady=(0, 5))
        self.strategy_var = tk.StringVar(value=self.config.get("strategy", ""))
        self.strategy_combo = ttk.Combobox(left, textvariable=self.strategy_var,
                                           state="readonly")
        self.strategy_combo.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(0, 10))

        self.router_frame = ttk.LabelFrame(left, text="REGIME ROUTER", padding=8)
        self.router_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.router_frame.grid_remove()

        ttk.Label(self.router_frame, text="TRENDING UP").grid(row=0, column=0, sticky="w", pady=2)
        self.trending_up_var = tk.StringVar(value=self.config.get("trending_up_strategy", "trend_macd"))
        self.trending_up_combo = ttk.Combobox(self.router_frame, textvariable=self.trending_up_var, state="readonly")
        self.trending_up_combo.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(self.router_frame, text="TRENDING DOWN").grid(row=1, column=0, sticky="w", pady=2)
        self.trending_down_var = tk.StringVar(value=self.config.get("trending_down_strategy", "trend_macd"))
        self.trending_down_combo = ttk.Combobox(self.router_frame, textvariable=self.trending_down_var, state="readonly")
        self.trending_down_combo.grid(row=1, column=1, sticky="ew", padx=5)

        ttk.Label(self.router_frame, text="RANGING").grid(row=2, column=0, sticky="w", pady=2)
        self.ranging_var = tk.StringVar(value=self.config.get("ranging_strategy", "range_rsi_bb"))
        self.ranging_combo = ttk.Combobox(self.router_frame, textvariable=self.ranging_var, state="readonly")
        self.ranging_combo.grid(row=2, column=1, sticky="ew", padx=5)

        ttk.Label(left, text="MODE").grid(row=5, column=0, sticky="w", pady=(8, 5))
        self.mode_var = tk.StringVar(value=self.config.get("mode", "balanced"))
        ttk.Combobox(left, textvariable=self.mode_var,
                     values=["conservative", "balanced", "aggressive"],
                     state="readonly") \
            .grid(row=5, column=1, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(left, text="RUN MODE").grid(row=6, column=0, sticky="w", pady=(0, 5))
        self.run_mode_var = tk.StringVar(value=self.config.get("run_mode", "Single"))
        self.run_mode_combo = ttk.Combobox(
            left,
            textvariable=self.run_mode_var,
            values=["Single", "All Strategies", "All Assets"],
            state="readonly"
        )
        self.run_mode_combo.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(left, text="MAX CANDLES").grid(row=7, column=0, sticky="w", pady=(0, 5))
        self.candles_var = tk.IntVar(value=self.config.get("candles", 0))
        ttk.Entry(left, textvariable=self.candles_var) \
            .grid(row=7, column=1, columnspan=2, sticky="ew", pady=(0, 10))

        self.equity_var = tk.BooleanVar(value=self.config.get("show_equity", True))
        ttk.Checkbutton(left, text="Show Equity Curve",
                        variable=self.equity_var,
                        command=self.toggle_equity_area) \
            .grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.use_router_var = tk.BooleanVar(value=self.config.get("use_router", False))
        ttk.Checkbutton(left, text="Use Regime Router",
                        variable=self.use_router_var,
                        command=self.toggle_router_ui) \
            .grid(row=9, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Button(left, text="RUN BACKTEST", command=self.run_backtest) \
            .grid(row=10, column=0, columnspan=3, pady=(10, 0))

        # ------------------------------------------------------------------ #
        # RIGHT SIDE: output + risk sliders + equity plot
        # ------------------------------------------------------------------ #
        right = ttk.Frame(self.root, padding="20")
        right.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.root.grid_columnconfigure(1, weight=3)

        # Text output
        self.output_text = scrolledtext.ScrolledText(
            right,
            wrap=tk.WORD,
            bg="#0d1117",
            fg="#c9d1d9",
            font=('Consolas', 14)
        )
        self.output_text.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        right.grid_rowconfigure(0, weight=2)

        # Risk sliders live here now
        risk_frame = ttk.LabelFrame(right, text="RISK / POSITION SETTINGS", padding=10)
        risk_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.position_pct_var = tk.DoubleVar(value=self.config.get("position_pct", 15.0))
        ttk.Label(risk_frame, text="Position size (% of equity)") \
            .grid(row=0, column=0, sticky="w")
        tk.Scale(
            risk_frame,
            from_=1.0,
            to=100.0,
            orient=tk.HORIZONTAL,
            resolution=1.0,
            variable=self.position_pct_var,
            length=400,
            showvalue=True,
            bg="#0d1117",
            fg="#c9d1d9",
            highlightthickness=0,
            font=('Consolas', 12)
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        self.risk_pct_var = tk.DoubleVar(value=self.config.get("risk_pct", 1.0))
        ttk.Label(risk_frame, text="Risk per trade (% of equity)") \
            .grid(row=1, column=0, sticky="w")
        tk.Scale(
            risk_frame,
            from_=0.5,
            to=5.0,
            orient=tk.HORIZONTAL,
            resolution=0.1,
            variable=self.risk_pct_var,
            length=400,
            showvalue=True,
            bg="#0d1117",
            fg="#c9d1d9",
            highlightthickness=0,
            font=('Consolas', 12)
        ).grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        self.rr_var = tk.DoubleVar(value=self.config.get("reward_rr", 1.5))
        ttk.Label(risk_frame, text="Reward : Risk") \
            .grid(row=2, column=0, sticky="w")
        tk.Scale(
            risk_frame,
            from_=0.5,
            to=5.0,
            orient=tk.HORIZONTAL,
            resolution=0.25,
            variable=self.rr_var,
            length=400,
            showvalue=True,
            bg="#0d1117",
            fg="#c9d1d9",
            highlightthickness=0,
            font=('Consolas', 12)
        ).grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        # Copy output button
        ttk.Button(right, text="COPY OUTPUT", command=self.copy_output) \
            .grid(row=2, column=0, sticky="w", pady=(0, 10))

        # Equity plot
        self.fig = Figure(figsize=(12, 4), dpi=100, facecolor="#0d1117")
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().grid(row=3, column=0, columnspan=2,
                                         sticky="nsew", pady=10)
        right.grid_rowconfigure(3, weight=1)

    # ------------------------------------------------------------------ #
    # UI TOGGLES
    # ------------------------------------------------------------------ #
    def toggle_router_ui(self):
        if self.use_router_var.get():
            self.router_frame.grid()
            self.strategy_combo.configure(state="disabled")
            if self.run_mode_var.get() == "All Strategies":
                self.run_mode_var.set("Single")
            self.run_mode_combo['values'] = ["Single", "All Assets"]
        else:
            self.router_frame.grid_remove()
            self.strategy_combo.configure(state="readonly")
            self.run_mode_combo['values'] = ["Single", "All Strategies", "All Assets"]
        self.save_config()

    def toggle_equity_area(self):
        if self.equity_var.get():
            self.canvas.get_tk_widget().grid()
        else:
            self.canvas.get_tk_widget().grid_remove()
        self.save_config()

    # ------------------------------------------------------------------ #
    # DATA / STRATEGY LOADING
    # ------------------------------------------------------------------ #
    def scan_data_files(self):
        if not os.path.exists(MANIFEST_FILE):
            return
        with open(MANIFEST_FILE, 'r') as f:
            manifest = json.load(f)
        tf = self.timeframe_var.get()
        items = []
        for pair, data in manifest["pairs"].items():
            if tf in data:
                items.append((data[tf]["file"], data[tf]["candles"]))

        self.file_combo['values'] = [f"{f[0]} ({f[1]} candles)" for f in items]
        if items and not self.file_var.get():
            self.file_combo.current(0)
            self.file_var.set(items[0][0])

    def load_strategies(self):
        load_strategies()
        strat_list = list_strategies()
        for combo in (self.strategy_combo, self.trending_up_combo,
                      self.trending_down_combo, self.ranging_combo):
            combo['values'] = strat_list
        if strat_list:
            self.strategy_combo.set(self.config.get("strategy", strat_list[0]))
            self.trending_up_combo.set(self.config.get("trending_up_strategy", strat_list[0]))
            self.trending_down_combo.set(self.config.get("trending_down_strategy", strat_list[0]))
            self.ranging_combo.set(self.config.get("ranging_strategy", strat_list[0]))

    # ------------------------------------------------------------------ #
    # RUN LOGIC
    # ------------------------------------------------------------------ #
    def run_backtest(self):
        self.save_config()
        self.output_text.delete(1.0, tk.END)
        self.fig.clear()

        run_mode = self.run_mode_var.get()
        use_router = self.use_router_var.get()
        mode = self.mode_var.get()
        tf = self.timeframe_var.get()
        max_c = int(self.candles_var.get() or 0)

        # Read current slider values
        position_pct = float(self.position_pct_var.get())
        risk_pct = float(self.risk_pct_var.get())
        reward_rr = float(self.rr_var.get())

        mappings = None
        if use_router:
            mappings = {
                "trending_up": self.trending_up_var.get(),
                "trending_down": self.trending_down_var.get(),
                "ranging": self.ranging_var.get()
            }

        if run_mode == "Single":
            self._run_single(mode, use_router, max_c, mappings,
                             position_pct, risk_pct, reward_rr)
        elif run_mode == "All Strategies":
            self._run_all_strategies(mode, use_router, max_c, mappings,
                                     position_pct, risk_pct, reward_rr)
        elif run_mode == "All Assets":
            self._run_all_assets(mode, use_router, max_c, tf, mappings,
                                 position_pct, risk_pct, reward_rr)

    # ------------------------------------------------------------------ #
    # SINGLE RUN
    # ------------------------------------------------------------------ #
    def _run_single(self, mode, use_router, max_c, mappings,
                    position_pct, risk_pct, reward_rr):
        sel = self.file_var.get()
        if not sel:
            messagebox.showerror("Error", "No data file selected")
            return
        asset = sel.split(" (")[0]
        path = os.path.join(DATA_DIR, asset)
        strat = self.strategy_var.get()

        try:
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            self.output_text.insert(tk.END,
                f"Loaded {len(df):,} rows from {os.path.basename(path)}\n\n")
        except Exception as e:
            messagebox.showerror("CSV Error", f"Failed to load CSV:\n{e}")
            return

        try:
            df = add_indicators_and_regime(df)
            if df.empty:
                messagebox.showerror("Error", "No data after indicators")
                return
            self.output_text.insert(tk.END,
                f"Indicators ready: {len(df):,} valid rows\n\n")
        except Exception as e:
            messagebox.showerror("Indicator Error",
                                 f"Failed to compute indicators:\n{e}")
            return

        if max_c and max_c < len(df):
            df = df.tail(max_c)

        self.output_text.insert(tk.END,
            f"Starting backtest…\n"
            f"{self._make_header(asset, strat, use_router)}\n"
            f"Mode: {mode}\n"
            f"Using last {len(df)} candles\n\n")
        self.root.update()

        try:
            summary, result = run_backtest(
                df,
                mode,
                strat,
                use_router=use_router,
                strategy_mappings=mappings,
                position_pct=position_pct,
                risk_pct=risk_pct,
                reward_rr=reward_rr,
            )
            result.asset = asset.split("_")[0]
            result.save_trades(RESULTS_DIR)

            lines = summary.splitlines()
            lines[1] = self._make_header(asset, strat, use_router)
            self.summary = "\n".join(lines)
            self.output_text.insert(tk.END, self.summary)

            if self.equity_var.get() and result.trades:
                self.plot_equity_curve(result.trades)

            self.output_text.insert(tk.END, "\nBacktest completed.\n")
        except Exception as e:
            err = f"\nBACKTEST FAILED:\n{traceback.format_exc()}"
            self.output_text.insert(tk.END, err)
            messagebox.showerror("Backtest Failed", "Check output.")

    # ------------------------------------------------------------------ #
    # ALL STRATEGIES
    # ------------------------------------------------------------------ #
    def _run_all_strategies(self, mode, use_router, max_c, mappings,
                            position_pct, risk_pct, reward_rr):
        sel = self.file_var.get()
        if not sel:
            messagebox.showerror("Error", "No data file selected")
            return
        asset = sel.split(" (")[0]
        path = os.path.join(DATA_DIR, asset)

        try:
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = add_indicators_and_regime(df)
            if max_c and max_c < len(df):
                df = df.tail(max_c)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load/process data:\n{e}")
            return

        results = []
        for s in list_strategies():
            try:
                summ, _ = run_backtest(
                    df,
                    mode,
                    s,
                    use_router=False,
                    strategy_mappings=None,
                    position_pct=position_pct,
                    risk_pct=risk_pct,
                    reward_rr=reward_rr,
                )
                final = float(re.search(r'Final: \$([\d,]+\.\d+)', summ).group(1).replace(",", ""))
                ret   = float(re.search(r'Return: ([\-\+\d\.]+)%', summ).group(1))
                trd   = int(re.search(r'Trades: (\d+)', summ).group(1))
                ddpc  = float(re.search(r'\((\d+\.\d+)%\)', summ).group(1))
                results.append({"Strategy": s, "Final": final,
                                "Return %": ret, "Trades": trd,
                                "Max DD %": ddpc})
            except Exception as e:
                self.output_text.insert(tk.END, f"Error on {s}: {str(e)}\n")

        if results:
            df_res = pd.DataFrame(results)
            self.output_text.insert(tk.END,
                "All Strategies Summary:\n" + df_res.to_string(index=False) + "\n\n")
        else:
            self.output_text.insert(tk.END, "No valid results.\n")

    # ------------------------------------------------------------------ #
    # ALL ASSETS
    # ------------------------------------------------------------------ #
    def _run_all_assets(self, mode, use_router, max_c, tf, mappings,
                        position_pct, risk_pct, reward_rr):
        strat = self.strategy_var.get()
        if not strat:
            messagebox.showerror("Error", "No strategy selected")
            return
        if not os.path.exists(MANIFEST_FILE):
            messagebox.showerror("Error", "No manifest.json")
            return

        with open(MANIFEST_FILE, 'r') as f:
            manifest = json.load(f)

        results = []
        for pair, data in manifest["pairs"].items():
            if tf not in data:
                continue
            file = data[tf]["file"]
            path = os.path.join(DATA_DIR, file)
            try:
                df = pd.read_csv(path)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                df = add_indicators_and_regime(df)
                if max_c and max_c < len(df):
                    df = df.tail(max_c)

                summ, result = run_backtest(
                    df,
                    mode,
                    strat,
                    use_router=use_router,
                    strategy_mappings=mappings,
                    position_pct=position_pct,
                    risk_pct=risk_pct,
                    reward_rr=reward_rr,
                )
                result.asset = pair
                result.save_trades(RESULTS_DIR)

                lines = summ.splitlines()
                lines[1] = self._make_header(file, "router" if use_router else strat,
                                             use_router)
                summ = "\n".join(lines)

                final = float(re.search(r'Final: \$([\d,]+\.\d+)', summ).group(1).replace(",", ""))
                ret   = float(re.search(r'Return: ([\-\+\d\.]+)%', summ).group(1))
                trd   = int(re.search(r'Trades: (\d+)', summ).group(1))
                ddpc  = float(re.search(r'\((\d+\.\d+)%\)', summ).group(1))
                results.append({"Asset": pair, "Final": final,
                                "Return %": ret, "Trades": trd,
                                "Max DD %": ddpc})
            except Exception as e:
                self.output_text.insert(tk.END, f"Error on {pair}: {str(e)}\n")

        if results:
            df_res = pd.DataFrame(results)
            self.output_text.insert(tk.END,
                "All Assets Summary:\n" + df_res.to_string(index=False) + "\n\n")
        else:
            self.output_text.insert(tk.END, "No valid results.\n")

    # ------------------------------------------------------------------ #
    # EQUITY PLOT (single run)
    # ------------------------------------------------------------------ #
    def plot_equity_curve(self, trades):
        ax = self.fig.add_subplot(111)
        ax.clear()
        equity = [Decimal("100.0")]
        capital = Decimal("100.0")
        for t in trades:
            if t.exit_reason != "end_of_simulation":
                capital += t.pnl
            equity.append(capital)
        ax.plot(equity, color='#ffea00', linewidth=2, label="Equity")
        ax.set_facecolor('#0d1b2a')
        ax.grid(True, color='#1f6aa5', linestyle='--', alpha=0.5)
        ax.set_title("Equity Curve", color='white', fontsize=12)
        ax.set_xlabel("Trade #", color='white', fontsize=10)
        ax.set_ylabel("Value ($)", color='white', fontsize=10)
        ax.tick_params(colors='white', labelsize=9)
        ax.legend(facecolor='#1f1f1f', edgecolor='#ffea00',
                  labelcolor='white', fontsize=9)
        self.fig.tight_layout()
        self.canvas.draw()

    # ------------------------------------------------------------------ #
    # COPY OUTPUT
    # ------------------------------------------------------------------ #
    def copy_output(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.summary)
        messagebox.showinfo("Copied", "Output copied!")


if __name__ == "__main__":
    root = tk.Tk()
    app = BacktesterGUI(root)
    root.mainloop()

# backtester.py v0.4 (641 lines)
