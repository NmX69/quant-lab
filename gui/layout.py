# gui/layout.py
# Purpose: Build the left (controls) and right (output) panels for BacktesterGUI.
# Major External Functions/Classes: create_left_panel, create_right_panel
# Notes: Mutates the passed gui instance, attaching widget attributes.

from typing import Any

import tkinter as tk
from tkinter import ttk, scrolledtext
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def create_left_panel(gui: Any) -> None:
    """
    Build the left-hand control panel and attach variables/widgets to `gui`.
    Expects `gui.root` and `gui.config` to be set.
    """
    left = ttk.Frame(gui.root, padding="20")
    left.grid(row=0, column=0, sticky="ns", padx=20, pady=20)
    gui.root.grid_columnconfigure(0, weight=1)
    gui.root.grid_rowconfigure(0, weight=1)

    ttk.Label(
        left,
        text="REGIME BACKTESTER",
        font=("Consolas", 20, "bold"),
        foreground="#58a6ff",
    ).grid(row=0, column=0, columnspan=3, pady=(0, 20))

    ttk.Label(left, text="TIMEFRAME").grid(row=1, column=0, sticky="w", pady=(0, 5))
    gui.timeframe_var = tk.StringVar(value=gui.config.get("timeframe", "1h"))
    ttk.Combobox(
        left,
        textvariable=gui.timeframe_var,
        values=["1h"],
        state="readonly",
    ).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(0, 10))

    ttk.Label(left, text="DATA FILE").grid(row=2, column=0, sticky="w", pady=(0, 5))
    gui.file_var = tk.StringVar(value=gui.config.get("data_file", ""))
    gui.file_combo = ttk.Combobox(left, textvariable=gui.file_var, state="readonly")
    gui.file_combo.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(0, 10))

    ttk.Label(left, text="STRATEGY").grid(row=3, column=0, sticky="w", pady=(0, 5))
    gui.strategy_var = tk.StringVar(value=gui.config.get("strategy", "range_mean_reversion"))
    gui.strategy_combo = ttk.Combobox(
        left,
        textvariable=gui.strategy_var,
        values=[],
        state="readonly",
    )
    gui.strategy_combo.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(0, 10))

    gui.router_frame = ttk.LabelFrame(left, text="REGIME ROUTER", padding=8)
    gui.router_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
    gui.router_frame.grid_remove()

    ttk.Label(gui.router_frame, text="TRENDING UP").grid(
        row=0, column=0, sticky="w", pady=2
    )
    gui.trending_up_var = tk.StringVar(
        value=gui.config.get("trending_up_strategy", "trend_macd")
    )
    gui.trending_up_combo = ttk.Combobox(
        gui.router_frame, textvariable=gui.trending_up_var, state="readonly"
    )
    gui.trending_up_combo.grid(row=0, column=1, sticky="ew", padx=5)

    ttk.Label(gui.router_frame, text="TRENDING DOWN").grid(
        row=1, column=0, sticky="w", pady=2
    )
    gui.trending_down_var = tk.StringVar(
        value=gui.config.get("trending_down_strategy", "trend_macd")
    )
    gui.trending_down_combo = ttk.Combobox(
        gui.router_frame, textvariable=gui.trending_down_var, state="readonly"
    )
    gui.trending_down_combo.grid(row=1, column=1, sticky="ew", padx=5)

    ttk.Label(gui.router_frame, text="RANGING").grid(
        row=2, column=0, sticky="w", pady=2
    )
    gui.ranging_var = tk.StringVar(
        value=gui.config.get("ranging_strategy", "range_mean_reversion")
    )
    gui.ranging_combo = ttk.Combobox(
        gui.router_frame, textvariable=gui.ranging_var, state="readonly"
    )
    gui.ranging_combo.grid(row=2, column=1, sticky="ew", padx=5)

    ttk.Label(left, text="RUN MODE").grid(row=5, column=0, sticky="w", pady=(10, 5))
    gui.run_mode_var = tk.StringVar(value=gui.config.get("run_mode", "Single"))
    gui.run_mode_combo = ttk.Combobox(
        left,
        textvariable=gui.run_mode_var,
        values=["Single", "All Strategies", "All Assets"],
        state="readonly",
    )
    gui.run_mode_combo.grid(row=5, column=1, columnspan=2, sticky="ew", pady=(0, 10))

    ttk.Label(left, text="POSITION % OF EQUITY").grid(
        row=6, column=0, sticky="w", pady=(10, 5)
    )
    gui.position_pct_var = tk.DoubleVar(
        value=gui.config.get("position_pct", 15.0)
    )
    ttk.Scale(
        left,
        from_=1,
        to=50,
        orient="horizontal",
        variable=gui.position_pct_var,
        length=200,
    ).grid(row=6, column=1, sticky="ew", pady=(0, 5))
    ttk.Label(
        left,
        textvariable=tk.StringVar(
            value=f"{gui.position_pct_var.get():.1f}%"
        ),
    ).grid(row=6, column=2, sticky="w")

    ttk.Label(left, text="RISK % PER TRADE").grid(
        row=7, column=0, sticky="w", pady=(10, 5)
    )
    gui.risk_pct_var = tk.DoubleVar(
        value=gui.config.get("risk_pct", 1.0)
    )
    ttk.Scale(
        left,
        from_=0.25,
        to=5.0,
        orient="horizontal",
        variable=gui.risk_pct_var,
        length=200,
    ).grid(row=7, column=1, sticky="ew", pady=(0, 5))
    ttk.Label(
        left,
        textvariable=tk.StringVar(
            value=f"{gui.risk_pct_var.get():.2f}%"
        ),
    ).grid(row=7, column=2, sticky="w")

    ttk.Label(left, text="REWARD : RISK (RR)").grid(
        row=8, column=0, sticky="w", pady=(10, 5)
    )
    gui.rr_var = tk.DoubleVar(
        value=gui.config.get("reward_rr", 2.0)
    )
    ttk.Scale(
        left,
        from_=1.0,
        to=5.0,
        orient="horizontal",
        variable=gui.rr_var,
        length=200,
    ).grid(row=8, column=1, sticky="ew", pady=(0, 5))
    ttk.Label(
        left,
        textvariable=tk.StringVar(
            value=f"{gui.rr_var.get():.2f}x"
        ),
    ).grid(row=8, column=2, sticky="w")

    ttk.Label(left, text="MAX CANDLES (0 = all)").grid(
        row=9, column=0, sticky="w", pady=(10, 5)
    )
    gui.candles_var = tk.IntVar(value=gui.config.get("max_candles", 5000))
    ttk.Entry(left, textvariable=gui.candles_var, width=10).grid(
        row=9, column=1, sticky="w", pady=(0, 10)
    )

    gui.equity_var = tk.BooleanVar(value=gui.config.get("show_equity", True))
    ttk.Checkbutton(
        left,
        text="Show Equity Curve",
        variable=gui.equity_var,
        command=gui.toggle_equity_area,
    ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(0, 10))

    gui.use_router_var = tk.BooleanVar(value=gui.config.get("use_router", False))
    ttk.Checkbutton(
        left,
        text="Use Regime Router",
        variable=gui.use_router_var,
        command=gui.toggle_router_ui,
    ).grid(row=11, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Button(left, text="RUN BACKTEST", command=gui.run_backtest).grid(
        row=12, column=0, columnspan=3, pady=(10, 0)
    )


def create_right_panel(gui: Any) -> None:
    """
    Build the right-hand output panel (text, risk sliders, equity plot).
    Expects `gui.root` and `gui.config` to be set.
    """
    right = ttk.Frame(gui.root, padding="20")
    right.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
    gui.root.grid_columnconfigure(1, weight=3)
    gui.root.grid_rowconfigure(0, weight=1)

    right.grid_columnconfigure(0, weight=1)
    right.grid_columnconfigure(1, weight=0)

    gui.output_text = scrolledtext.ScrolledText(
        right,
        wrap="none",
        width=100,
        height=30,
        bg="#0d1117",
        fg="#c9d1d9",
        insertbackground="#c9d1d9",
        font=("Consolas", 11),
    )
    gui.output_text.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
    right.grid_rowconfigure(0, weight=1)

    ttk.Label(right, text="RISK SETTINGS SNAPSHOT").grid(
        row=1, column=0, sticky="w", pady=(0, 5)
    )
    gui.snapshot_label = ttk.Label(
        right,
        text="",
        font=("Consolas", 10),
    )
    gui.snapshot_label.grid(row=1, column=1, sticky="e", pady=(0, 5))

    gui.summary_label = ttk.Label(
        right,
        text="No backtest run yet.",
        font=("Consolas", 11),
        justify="left",
    )
    gui.summary_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))

    ttk.Button(right, text="COPY OUTPUT", command=gui.copy_output).grid(
        row=3, column=0, sticky="w", pady=(0, 10)
    )

    # Equity curve area lives inside its own frame so the main GUI
    # can show/hide it via BacktesterGUI._toggle_equity_area().
    gui.equity_frame = ttk.Frame(right)
    gui.equity_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=10)
    right.grid_rowconfigure(4, weight=1)

    gui.fig = Figure(figsize=(12, 4), dpi=100, facecolor="#0d1117")
    gui.canvas = FigureCanvasTkAgg(gui.fig, master=gui.equity_frame)
    gui.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    gui.equity_frame.grid_rowconfigure(0, weight=1)
    gui.equity_frame.grid_columnconfigure(0, weight=1)

# gui/layout.py v0.2 (255 lines)
