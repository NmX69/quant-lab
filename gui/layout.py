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
    gui.strategy_var = tk.StringVar(value=gui.config.get("strategy", ""))
    gui.strategy_combo = ttk.Combobox(
        left, textvariable=gui.strategy_var, state="readonly"
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
        value=gui.config.get("ranging_strategy", "range_rsi_bb")
    )
    gui.ranging_combo = ttk.Combobox(
        gui.router_frame, textvariable=gui.ranging_var, state="readonly"
    )
    gui.ranging_combo.grid(row=2, column=1, sticky="ew", padx=5)

    ttk.Label(left, text="MODE").grid(row=5, column=0, sticky="w", pady=(8, 5))
    gui.mode_var = tk.StringVar(value=gui.config.get("mode", "balanced"))
    ttk.Combobox(
        left,
        textvariable=gui.mode_var,
        values=["conservative", "balanced", "aggressive"],
        state="readonly",
    ).grid(row=5, column=1, columnspan=2, sticky="ew", pady=(0, 10))

    ttk.Label(left, text="RUN MODE").grid(row=6, column=0, sticky="w", pady=(0, 5))
    gui.run_mode_var = tk.StringVar(value=gui.config.get("run_mode", "Single"))
    gui.run_mode_combo = ttk.Combobox(
        left,
        textvariable=gui.run_mode_var,
        values=["Single", "All Strategies", "All Assets"],
        state="readonly",
    )
    gui.run_mode_combo.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(0, 10))

    ttk.Label(left, text="MAX CANDLES").grid(row=7, column=0, sticky="w", pady=(0, 5))
    gui.candles_var = tk.IntVar(value=gui.config.get("candles", 0))
    ttk.Entry(left, textvariable=gui.candles_var).grid(
        row=7, column=1, columnspan=2, sticky="ew", pady=(0, 10)
    )

    gui.equity_var = tk.BooleanVar(value=gui.config.get("show_equity", True))
    ttk.Checkbutton(
        left,
        text="Show Equity Curve",
        variable=gui.equity_var,
        command=gui.toggle_equity_area,
    ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 10))

    gui.use_router_var = tk.BooleanVar(value=gui.config.get("use_router", False))
    ttk.Checkbutton(
        left,
        text="Use Regime Router",
        variable=gui.use_router_var,
        command=gui.toggle_router_ui,
    ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Button(left, text="RUN BACKTEST", command=gui.run_backtest).grid(
        row=10, column=0, columnspan=3, pady=(10, 0)
    )


def create_right_panel(gui: Any) -> None:
    """
    Build the right-hand output panel (text, risk sliders, equity plot).
    Expects `gui.root` and `gui.config` to be set.
    """
    right = ttk.Frame(gui.root, padding="20")
    right.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
    gui.root.grid_columnconfigure(1, weight=3)

    gui.output_text = scrolledtext.ScrolledText(
        right,
        wrap=tk.WORD,
        bg="#0d1117",
        fg="#c9d1d9",
        font=("Consolas", 14),
    )
    gui.output_text.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
    right.grid_rowconfigure(0, weight=2)

    risk_frame = ttk.LabelFrame(right, text="RISK / POSITION SETTINGS", padding=10)
    risk_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

    gui.position_pct_var = tk.DoubleVar(value=gui.config.get("position_pct", 15.0))
    ttk.Label(risk_frame, text="Position size (% of equity)").grid(
        row=0, column=0, sticky="w"
    )
    tk.Scale(
        risk_frame,
        from_=1.0,
        to=100.0,
        orient=tk.HORIZONTAL,
        resolution=1.0,
        variable=gui.position_pct_var,
        length=400,
        showvalue=True,
        bg="#0d1117",
        fg="#c9d1d9",
        highlightthickness=0,
        font=("Consolas", 12),
    ).grid(row=0, column=1, sticky="ew", padx=5, pady=2)

    gui.risk_pct_var = tk.DoubleVar(value=gui.config.get("risk_pct", 1.0))
    ttk.Label(risk_frame, text="Risk per trade (% of equity)").grid(
        row=1, column=0, sticky="w"
    )
    tk.Scale(
        risk_frame,
        from_=0.5,
        to=5.0,
        orient=tk.HORIZONTAL,
        resolution=0.1,
        variable=gui.risk_pct_var,
        length=400,
        showvalue=True,
        bg="#0d1117",
        fg="#c9d1d9",
        highlightthickness=0,
        font=("Consolas", 12),
    ).grid(row=1, column=1, sticky="ew", padx=5, pady=2)

    gui.rr_var = tk.DoubleVar(value=gui.config.get("reward_rr", 1.5))
    ttk.Label(risk_frame, text="Reward : Risk").grid(row=2, column=0, sticky="w")
    tk.Scale(
        risk_frame,
        from_=0.5,
        to=5.0,
        orient=tk.HORIZONTAL,
        resolution=0.25,
        variable=gui.rr_var,
        length=400,
        showvalue=True,
        bg="#0d1117",
        fg="#c9d1d9",
        highlightthickness=0,
        font=("Consolas", 12),
    ).grid(row=2, column=1, sticky="ew", padx=5, pady=2)

    ttk.Button(right, text="COPY OUTPUT", command=gui.copy_output).grid(
        row=2, column=0, sticky="w", pady=(0, 10)
    )

    gui.fig = Figure(figsize=(12, 4), dpi=100, facecolor="#0d1117")
    gui.canvas = FigureCanvasTkAgg(gui.fig, master=right)
    gui.canvas.get_tk_widget().grid(
        row=3, column=0, columnspan=2, sticky="nsew", pady=10
    )
    right.grid_rowconfigure(3, weight=1)

# gui/layout.py v0.1 (223 lines)
