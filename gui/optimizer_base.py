# gui/optimizer_base.py
# Purpose: Shared base class + helpers for all optimizer windows (C1, C2, C3).
# Major External APIs:
#   - OptimizerBaseWindow
#   - build_region_filter(parent, start_row, top_n_default="50", label="Region Filter (optional)")
#   - summarize_with_region(df, filter_ctx, status_label, status_prefix)
#   - parse_float_list(text, fallback)
#   - parse_strategy_values(text)
#   - parse_optional_float(text)
#   - parse_optional_int(text)

from __future__ import annotations

from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import ttk

import pandas as pd

from core.optimizer import select_good_region, summarize_region


class OptimizerBaseWindow:
    """
    Lightweight base for C1 / C2 / C3 optimizer windows.

    Holds references to the main GUI/root and exposes helpers for:
      - creating the Toplevel window
      - creating region filter
      - creating status/result widgets
      - simple .show() convenience
    """

    def __init__(self, gui: Any, title: str):
        self.gui = gui
        self.root = gui.root
        self.win = tk.Toplevel(self.root)
        self.win.title(title)
        self.win.configure(bg="#0d1117")

        self.status_label: Optional[ttk.Label] = None
        self.results_text: Optional[tk.Text] = None

    # ------------------------------------------------------------------ #
    # Common UI helpers
    # ------------------------------------------------------------------ #

    def create_region_filter(
        self,
        start_row: int,
        top_n_default: str = "50",
        label: str = "Region Filter (optional)",
    ) -> Dict[str, Any]:
        """
        Wrapper around build_region_filter using this window as parent.
        """
        return build_region_filter(
            parent=self.win,
            start_row=start_row,
            top_n_default=top_n_default,
            label=label,
        )

    def create_status_and_results(
        self,
        *,
        status_row: int,
        results_row: int,
        results_height: int = 25,
        results_width: int = 140,
    ) -> None:
        """
        Create standard status label + results text widget on this window.
        """
        status = ttk.Label(self.win, text="Ready.")
        status.grid(
            row=status_row,
            column=0,
            columnspan=2,
            sticky="w",
            padx=10,
            pady=(0, 5),
        )

        results = tk.Text(
            self.win,
            wrap="none",
            height=results_height,
            width=results_width,
            bg="#0d1117",
            fg="#c9d1d9",
        )
        results.grid(
            row=results_row,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=10,
            pady=(0, 5),
        )

        self.win.grid_rowconfigure(results_row, weight=1)
        self.win.grid_columnconfigure(1, weight=1)

        self.status_label = status
        self.results_text = results

    def show(self) -> None:
        """
        Bring window to front and grab focus (no new mainloop).
        """
        self.win.transient(self.root)
        try:
            self.win.grab_set()
        except Exception:
            # Not all Tk builds support grab_set from Toplevel; ignore.
            pass
        self.win.focus_set()


# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------


def parse_float_list(text: str, fallback: float) -> List[float]:
    """
    Parse a comma-separated list of floats. If parsing fails or result is empty,
    return [fallback].
    """
    text = (text or "").strip()
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


def parse_strategy_values(text: str) -> List[Any]:
    """
    Parse a comma-separated list of strategy parameter values.

    - Values containing '%' are kept as strings (e.g. "3%").
    - Other values are parsed as int/float when possible, otherwise left as strings.
    """
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split(",") if p.strip()]
    vals: List[Any] = []
    for v in parts:
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


def parse_optional_float(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def parse_optional_int(text: str) -> Optional[int]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


# ----------------------------------------------------------------------
# Region filter UI + logic (C4)
# ----------------------------------------------------------------------


def build_region_filter(
    parent: tk.Widget,
    start_row: int,
    top_n_default: str = "50",
    label: str = "Region Filter (optional)",
) -> Dict[str, Any]:
    """
    Create the common C4 region filter UI in a LabelFrame.

    Returns a dict containing:
      - frame
      - min_sharpe_var
      - max_dd_var
      - min_trades_var
      - min_return_var
      - top_n_var
      - apply_filter_var
      - next_row  (row index after the frame)
    """
    filter_frame = ttk.LabelFrame(parent, text=label, padding=8)
    filter_frame.grid(
        row=start_row,
        column=0,
        columnspan=2,
        sticky="ew",
        padx=10,
        pady=(0, 5),
    )

    min_sharpe_var = tk.StringVar()
    max_dd_var = tk.StringVar()
    min_trades_var = tk.StringVar()
    min_return_var = tk.StringVar()
    top_n_var = tk.StringVar(value=top_n_default)
    apply_filter_var = tk.BooleanVar(value=True)

    ttk.Label(filter_frame, text="Min Sharpe:").grid(row=0, column=0, sticky="w")
    ttk.Entry(filter_frame, width=8, textvariable=min_sharpe_var).grid(
        row=0, column=1, sticky="w", padx=4
    )

    ttk.Label(filter_frame, text="Max DD (%):").grid(row=0, column=2, sticky="w")
    ttk.Entry(filter_frame, width=8, textvariable=max_dd_var).grid(
        row=0, column=3, sticky="w", padx=4
    )

    ttk.Label(filter_frame, text="Min Trades:").grid(
        row=1, column=0, sticky="w", pady=(4, 0)
    )
    ttk.Entry(filter_frame, width=8, textvariable=min_trades_var).grid(
        row=1, column=1, sticky="w", padx=4, pady=(4, 0)
    )

    ttk.Label(filter_frame, text="Min Return (%):").grid(
        row=1, column=2, sticky="w", pady=(4, 0)
    )
    ttk.Entry(filter_frame, width=8, textvariable=min_return_var).grid(
        row=1, column=3, sticky="w", padx=4, pady=(4, 0)
    )

    ttk.Label(filter_frame, text="Top N:").grid(
        row=2, column=0, sticky="w", pady=(4, 0)
    )
    ttk.Entry(filter_frame, width=8, textvariable=top_n_var).grid(
        row=2, column=1, sticky="w", padx=4, pady=(4, 0)
    )

    ttk.Checkbutton(
        filter_frame,
        text="Apply filter & show Top N",
        variable=apply_filter_var,
    ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))

    return {
        "frame": filter_frame,
        "min_sharpe_var": min_sharpe_var,
        "max_dd_var": max_dd_var,
        "min_trades_var": min_trades_var,
        "min_return_var": min_return_var,
        "top_n_var": top_n_var,
        "apply_filter_var": apply_filter_var,
        "next_row": start_row + 1,
    }


def summarize_with_region(
    df: pd.DataFrame,
    filter_ctx: Dict[str, Any],
    status_label: ttk.Label,
    status_prefix: str,
) -> pd.DataFrame:
    """
    Apply the shared C4 region filter and summarize via Top N.

    - If apply_filter_var is True, filter first using select_good_region, then
      summarize with Top N.
    - If filter nukes everything, fall back to summarizing over the full table.
    - If apply_filter_var is False, summarize directly over df.

    Returns the DataFrame that should be displayed.
    """
    if df is None or df.empty:
        status_label.config(text=f"{status_prefix}: no results.")
        return df

    min_sharpe_var = filter_ctx["min_sharpe_var"]
    max_dd_var = filter_ctx["max_dd_var"]
    min_trades_var = filter_ctx["min_trades_var"]
    min_return_var = filter_ctx["min_return_var"]
    top_n_var = filter_ctx["top_n_var"]
    apply_filter_var = filter_ctx["apply_filter_var"]

    total = len(df)
    df_show = df
    filtered_count = total

    if apply_filter_var.get():
        min_sh = parse_optional_float(min_sharpe_var.get())
        max_dd = parse_optional_float(max_dd_var.get())
        min_tr = parse_optional_int(min_trades_var.get())
        min_ret = parse_optional_float(min_return_var.get())

        good = select_good_region(
            df,
            min_sharpe=min_sh,
            max_dd_pct=max_dd,
            min_trades=min_tr,
            min_return_pct=min_ret,
        )
        filtered_count = len(good)

        try:
            top_n = int(top_n_var.get())
        except Exception:
            top_n = 50

        if filtered_count > 0:
            df_show = summarize_region(good, top_n=top_n)
            status_label.config(
                text=f"{status_prefix}. Combos: {total}, passed filter: {filtered_count}."
            )
        else:
            # If filter nukes everything, fall back to full table but report that.
            df_show = summarize_region(df, top_n=top_n)
            status_label.config(
                text=f"{status_prefix}. Combos: {total}, passed filter: 0 (showing full table)."
            )
    else:
        try:
            top_n = int(top_n_var.get())
        except Exception:
            top_n = 50
        df_show = summarize_region(df, top_n=top_n)
        status_label.config(text=f"{status_prefix}. Combos: {total}.")

    return df_show


# gui/optimizer_base.py v0.2 (355 lines)
