# gui/fitness_window.py
# Purpose: Phase D Asset Fitness Tester window with run + results tabs.
# Major External Classes/Functions:
#   - FitnessTabbedWindow(tk.Toplevel)
#   - Uses core.asset_fitness.run_fitness_matrix, compute_stability_metrics, export_fitness_matrix
# Notes: Non-modal; launched from the main Backtester GUI.

from __future__ import annotations

import os
import glob
import json
import threading
import traceback
from typing import Any, Dict, List, Optional, Sequence
from numbers import Number  # NEW

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pandas as pd

from core.config_manager import RESULTS_DIR, MANIFEST_FILE
from core.asset_fitness import (
    run_fitness_matrix,
    compute_stability_metrics,
    export_fitness_matrix,
)
from core import strategy_loader
from gui.fitness_detail_window import FitnessDetailWindow
from gui import fitness_mapping_export


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _timeframe_sort_key(tf: str) -> tuple:
    """
    Sort timeframes logically: 15m < 1h < 4h < 1d < 1w, etc.
    Fallback puts unknown formats at the end.
    """
    try:
        unit = tf[-1].lower()
        value = int(tf[:-1])
    except Exception:
        return (99, 9999, tf)

    unit_order = {"m": 0, "h": 1, "d": 2, "w": 3}
    return (unit_order.get(unit, 50), value, tf)


def _format_value_3dp(val: Any) -> str:
    """Format values for table display: ints as ints, floats to 3 decimal places."""
    if pd.isna(val):
        return ""
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, Number):
        # Keep ints as plain ints, floats/Decimals to 3 decimals
        if isinstance(val, int):
            return str(val)
        try:
            return f"{float(val):.3f}"
        except Exception:
            return str(val)
    return str(val)


class FitnessTabbedWindow(tk.Toplevel):
    """Phase D Asset Fitness Tester – run scans and inspect results."""

    def __init__(self, owner: Any) -> None:
        # Resolve the actual Tk root for Toplevel parent.
        if isinstance(owner, (tk.Tk, tk.Toplevel)):
            parent = owner
        elif hasattr(owner, "root") and isinstance(getattr(owner, "root"), (tk.Tk, tk.Toplevel)):
            parent = owner.root
        elif hasattr(owner, "master") and isinstance(getattr(owner, "master"), (tk.Tk, tk.Toplevel)):
            parent = owner.master
        else:
            # Fallback to default root if available.
            if tk._default_root is None:
                raise RuntimeError(
                    "FitnessTabbedWindow must be constructed with a Tk root or a BacktesterGUI that has .root."
                )
            parent = tk._default_root

        super().__init__(parent)

        self.owner = owner
        self.title("Quant-Lab – Asset Fitness Tester (Phase D)")

        # Try to open maximized / full-screen
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._last_run_params: Dict[str, Any] = {}

        self._full_df: Optional[pd.DataFrame] = None
        self._current_df: Optional[pd.DataFrame] = None
        self._top5_ids: Sequence[int] = []

        self._style = ttk.Style(self)

        # Single detail window reused for double-clicks
        self._detail_window: Optional[FitnessDetailWindow] = None

        self._build_ui()
        self._load_latest_results()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Styles for notebook tabs
        self._style.configure(
            "Fitness.TNotebook",
            background="#003366",
        )
        self._style.configure(
            "Fitness.TNotebook.Tab",
            foreground="yellow",
            background="#003366",
            padding=(10, 4),
        )
        self._style.map(
            "Fitness.TNotebook.Tab",
            background=[("selected", "#001a33"), ("active", "#002244")],
            foreground=[("selected", "yellow"), ("active", "yellow")],
        )

        # Treeview: dark grey background, white text
        self._style.configure(
            "Fitness.Treeview",
            background="#333333",
            foreground="white",
            fieldbackground="#333333",
            rowheight=24,
        )
        self._style.map(
            "Fitness.Treeview",
            background=[("selected", "#0060c0")],
            foreground=[("selected", "white")],
        )
        self._style.configure(
            "Fitness.Treeview.Heading",
            background="#222244",
            foreground="white",
        )

        # Progress bar: bright green bar on dark trough
        self._style.configure(
            "Fitness.Horizontal.TProgressbar",
            troughcolor="#222222",
            background="#00ff00",
            bordercolor="#222222",
            lightcolor="#00ff00",
            darkcolor="#008800",
        )

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self, style="Fitness.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")

        self.notebook = notebook

        self.run_frame = ttk.Frame(notebook)
        self.results_frame = ttk.Frame(notebook)

        notebook.add(self.run_frame, text="Run Scan")
        notebook.add(self.results_frame, text="Results")

        self._build_run_tab()
        self._build_results_tab()

    # ---------------------- Run Tab -----------------------------------

    def _build_run_tab(self) -> None:
        f = self.run_frame
        for col in range(4):
            f.columnconfigure(col, weight=1)
        for row in range(8):
            f.rowconfigure(row, weight=0)
        f.rowconfigure(8, weight=1)

        # Strategies (multi-select)
        ttk.Label(f, text="Strategies:").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        self.strategy_listbox = tk.Listbox(f, selectmode=tk.MULTIPLE, height=6, exportselection=False)
        self.strategy_listbox.grid(row=1, column=0, rowspan=3, sticky="nsew", padx=8, pady=2)

        strategies = self._load_strategy_names()
        for s in strategies:
            self.strategy_listbox.insert(tk.END, s)

        # Timeframes (multi-select)
        ttk.Label(f, text="Timeframes:").grid(row=0, column=1, sticky="w", padx=8, pady=(8, 2))
        self.timeframe_listbox = tk.Listbox(f, selectmode=tk.MULTIPLE, height=6, exportselection=False)
        self.timeframe_listbox.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=8, pady=2)

        timeframes = self._load_available_timeframes()
        for tf in timeframes:
            self.timeframe_listbox.insert(tk.END, tf)

        # Mode and router
        ttk.Label(f, text="Mode:").grid(row=0, column=2, sticky="w", padx=8, pady=(8, 2))
        self.mode_var = tk.StringVar(value="balanced")
        ttk.Entry(f, textvariable=self.mode_var).grid(row=1, column=2, sticky="ew", padx=8, pady=2)

        self.use_router_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f, text="Use Regime Router (core router config)", variable=self.use_router_var
        ).grid(row=2, column=2, sticky="w", padx=8, pady=2)

        # Position %, Risk %, Reward:Risk
        sliders_frame = ttk.LabelFrame(f, text="Sizing & Risk")
        sliders_frame.grid(row=0, column=3, rowspan=4, sticky="nsew", padx=8, pady=8)
        for i in range(3):
            sliders_frame.rowconfigure(i, weight=0)
        sliders_frame.columnconfigure(0, weight=1)

        # Position %
        ttk.Label(sliders_frame, text="Position % of Equity:").grid(
            row=0, column=0, sticky="w", padx=6, pady=(4, 0)
        )
        self.position_pct_var = tk.DoubleVar(value=15.0)
        tk.Scale(
            sliders_frame,
            from_=1.0,
            to=100.0,
            orient=tk.HORIZONTAL,
            resolution=1.0,
            variable=self.position_pct_var,
            length=220,
        ).grid(row=1, column=0, sticky="ew", padx=6, pady=2)

        # Risk %
        ttk.Label(sliders_frame, text="Risk % per Trade:").grid(
            row=2, column=0, sticky="w", padx=6, pady=(8, 0)
        )
        self.risk_pct_var = tk.DoubleVar(value=1.0)
        tk.Scale(
            sliders_frame,
            from_=0.1,
            to=10.0,
            orient=tk.HORIZONTAL,
            resolution=0.1,
            variable=self.risk_pct_var,
            length=220,
        ).grid(row=3, column=0, sticky="ew", padx=6, pady=2)

        # Reward:Risk
        ttk.Label(sliders_frame, text="Reward:Risk (RR):").grid(
            row=4, column=0, sticky="w", padx=6, pady=(8, 0)
        )
        self.rr_var = tk.DoubleVar(value=2.0)
        tk.Scale(
            sliders_frame,
            from_=0.5,
            to=10.0,
            orient=tk.HORIZONTAL,
            resolution=0.1,
            variable=self.rr_var,
            length=220,
        ).grid(row=5, column=0, sticky="ew", padx=6, pady=2)

        self.use_default_rr_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            sliders_frame,
            text="Use strategy default RR (ignore slider)",
            variable=self.use_default_rr_var,
        ).grid(row=6, column=0, sticky="w", padx=6, pady=(4, 6))

        # Tag
        ttk.Label(f, text="Tag (optional):").grid(row=4, column=0, sticky="w", padx=8, pady=(12, 2))
        self.tag_var = tk.StringVar(value="")
        ttk.Entry(f, textvariable=self.tag_var).grid(row=5, column=0, sticky="ew", padx=8, pady=2)

        # Run button + progress
        button_frame = ttk.Frame(f)
        button_frame.grid(row=6, column=0, columnspan=4, sticky="ew", padx=8, pady=(16, 4))
        button_frame.columnconfigure(0, weight=0)
        button_frame.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(button_frame, text="Run Fitness Scan", command=self._on_run_clicked)
        self.run_button.grid(row=0, column=0, sticky="w", padx=(0, 8))

        # Short, bright green progress bar (about ~30 "chars" wide)
        self.progress = ttk.Progressbar(
            button_frame,
            mode="indeterminate",
            length=300,
            style="Fitness.Horizontal.TProgressbar",
        )
        self.progress.grid(row=0, column=1, sticky="w", padx=(0, 4))

    # ---------------------- Results Tab --------------------------------

    def _build_results_tab(self) -> None:
        f = self.results_frame
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        # Filter + buttons
        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(1, weight=1)

        ttk.Label(
            top,
            text="Filter (asset/strategy/timeframe):",
        ).grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.filter_var = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.filter_var).grid(row=0, column=1, sticky="ew", padx=(0, 4))

        ttk.Button(top, text="Apply Filter", command=self._apply_filter).grid(
            row=0, column=2, sticky="w", padx=(0, 4)
        )
        ttk.Button(top, text="Clear Filter", command=self._clear_filter).grid(
            row=0, column=3, sticky="w", padx=(0, 4)
        )

        ttk.Button(top, text="Export CSV", command=self._export_csv).grid(
            row=0, column=4, sticky="w", padx=(12, 4)
        )
        ttk.Button(top, text="Export JSON", command=self._export_json).grid(
            row=0, column=5, sticky="w", padx=(0, 4)
        )
        ttk.Button(top, text="Export Mapping", command=self._export_mapping).grid(
            row=0, column=6, sticky="w", padx=(12, 4)
        )

        ttk.Button(top, text="Re-run Scan", command=self._on_rerun).grid(
            row=0, column=7, sticky="w", padx=(12, 0)
        )

        # Treeview
        tree_frame = ttk.Frame(f)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, show="headings", style="Fitness.Treeview")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Tag styles
        self.tree.tag_configure("default", background="#333333", foreground="white")
        self.tree.tag_configure("top5", background="#4a6d4a", foreground="white")

        # Double-click on row -> open detail popup
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        self._sort_column: Optional[str] = None
        self._sort_reverse: bool = False

    # ------------------------------------------------------------------
    # Helpers: data loading and UI state
    # ------------------------------------------------------------------

    def _load_strategy_names(self) -> List[str]:
        """Load strategy keys from core.strategy_loader."""
        try:
            strategy_loader.load_strategies()
            names = sorted(strategy_loader._STRATEGIES.keys())
            return names
        except Exception:
            return []

    def _load_available_timeframes(self) -> List[str]:
        """
        Load available timeframes from data/manifest.json via MANIFEST_FILE,
        and only include those that actually have at least one existing data file.
        """
        timeframes_with_data: set[str] = set()

        try:
            if os.path.exists(MANIFEST_FILE):
                base_dir = os.path.dirname(MANIFEST_FILE)
                with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                def _check_entry(entry: Dict[str, Any]) -> None:
                    tf = entry.get("timeframe") or entry.get("tf")
                    file_ = entry.get("file")
                    if isinstance(tf, str) and tf.strip() and isinstance(file_, str) and file_.strip():
                        tf_local = tf.strip()
                        file_local = file_.strip()
                        if not os.path.isabs(file_local):
                            file_path = os.path.join(base_dir, file_local)
                        else:
                            file_path = file_local
                        if os.path.exists(file_path):
                            timeframes_with_data.add(tf_local)

                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict):
                            _check_entry(entry)
                elif isinstance(data, dict):
                    for _key, val in data.items():
                        if isinstance(val, list):
                            for entry in val:
                                if isinstance(entry, dict):
                                    _check_entry(entry)
                        elif isinstance(val, dict):
                            _check_entry(val)
        except Exception:
            timeframes_with_data = set()

        if not timeframes_with_data:
            timeframes_with_data.add("1h")

        return sorted(timeframes_with_data, key=_timeframe_sort_key)

    def _get_latest_fitness_csv(self) -> Optional[str]:
        fitness_dir = os.path.join(RESULTS_DIR, "fitness")
        pattern = os.path.join(fitness_dir, "fitness_matrix_*.csv")
        files = glob.glob(pattern)
        if not files:
            return None
        files.sort(key=os.path.getmtime, reverse=True)
        return files[0]

    def _load_latest_results(self) -> None:
        path = self._get_latest_fitness_csv()
        if path:
            self._load_results_from_path(path)

    def _load_results_from_path(self, csv_path: str) -> None:
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            messagebox.showerror("Fitness Results", f"Failed to load fitness CSV:\n{csv_path}\n\n{exc}")
            return

        df = df.copy()
        df.insert(0, "__row_id", range(len(df)))
        self._full_df = df
        self._current_df = df

        if "fitness_score" in df.columns:
            try:
                fs = pd.to_numeric(df["fitness_score"], errors="coerce")
                order = fs.sort_values(ascending=False).index[:5]
                self._top5_ids = df.loc[order, "__row_id"].tolist()
            except Exception:
                self._top5_ids = []
        else:
            self._top5_ids = []

        self._refresh_tree()
        self._load_config_for_csv(csv_path)

    def _load_config_for_csv(self, csv_path: str) -> None:
        """Given a fitness_matrix CSV path, try to load its saved run config."""
        try:
            base = os.path.basename(csv_path)
            if not (base.startswith("fitness_matrix_") and base.endswith(".csv")):
                return
            tag = base[len("fitness_matrix_") : -4]
            fitness_dir = os.path.dirname(csv_path)
            cfg_path = os.path.join(fitness_dir, f"fitness_config_{tag}.json")
            if not os.path.exists(cfg_path):
                return

            with open(cfg_path, "r", encoding="utf-8") as f:
                params = json.load(f)
            if isinstance(params, dict):
                self._restore_run_params_from_dict(params)
        except Exception:
            return

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())

        if self._current_df is None or self._current_df.empty:
            self.tree["columns"] = []
            return

        df = self._current_df
        cols = [c for c in df.columns if c != "__row_id"]

        existing_cols = list(self.tree["columns"])
        first_time = existing_cols != cols

        if first_time:
            self.tree["columns"] = cols
            for col in cols:
                self.tree.heading(col, text=col, command=lambda c=col: self._on_tree_heading_click(c))
                self.tree.column(col, width=140, anchor="center")
        else:
            # Only update headings & commands; keep widths
            for col in cols:
                self.tree.heading(col, text=col, command=lambda c=col: self._on_tree_heading_click(c))

        for _, row in df.iterrows():
            row_id = row.get("__row_id")
            values = [_format_value_3dp(row.get(c)) for c in cols]
            tags = ["default"]
            if row_id in self._top5_ids:
                tags.append("top5")
            iid = str(int(row_id)) if row_id is not None else ""
            self.tree.insert("", tk.END, iid=iid, values=values, tags=tags)

    # ------------------------------------------------------------------
    # Run Scan handling
    # ------------------------------------------------------------------

    def _collect_run_params(self) -> Optional[Dict[str, Any]]:
        strat_indices = self.strategy_listbox.curselection()
        strategies = [self.strategy_listbox.get(i) for i in strat_indices]

        tf_indices = self.timeframe_listbox.curselection()
        timeframes = [self.timeframe_listbox.get(i) for i in tf_indices]

        if not strategies:
            messagebox.showerror("Fitness Scan", "Please select at least one strategy.")
            return None
        if not timeframes:
            messagebox.showerror("Fitness Scan", "Please select at least one timeframe.")
            return None

        mode = self.mode_var.get().strip() or "balanced"
        use_router = bool(self.use_router_var.get())

        position_pct = float(self.position_pct_var.get())
        risk_pct = float(self.risk_pct_var.get())

        if self.use_default_rr_var.get():
            reward_rr = None
        else:
            reward_rr = float(self.rr_var.get())

        tag = self.tag_var.get().strip()
        if not tag:
            tf_tag = "_".join(timeframes)
            tag = f"gui_{mode}_{tf_tag}"

        params: Dict[str, Any] = {
            "strategies": strategies,
            "timeframes": timeframes,
            "mode": mode,
            "use_router": use_router,
            "max_candles": 0,
            "position_pct": position_pct,
            "risk_pct": risk_pct,
            "reward_rr": reward_rr,
            "tag": tag,
        }
        return params

    def _on_run_clicked(self) -> None:
        if self._is_running:
            return

        params = self._collect_run_params()
        if params is None:
            return

        self._is_running = True
        self._last_run_params = params
        self.run_button.config(state=tk.DISABLED)
        self.progress.start(10)

        self._worker_thread = threading.Thread(
            target=self._run_scan_worker, args=(params,), daemon=True
        )
        self._worker_thread.start()

    def _run_scan_worker(self, params: Dict[str, Any]) -> None:
        try:
            df = run_fitness_matrix(
                strategies=params["strategies"],
                timeframes=params["timeframes"],
                mode=params["mode"],
                use_router=params["use_router"],
                max_candles=params["max_candles"],
                strategy_mappings=None,
                position_pct=params["position_pct"],
                risk_pct=params["risk_pct"],
                reward_rr=params["reward_rr"],
                assets=None,
            )

            df = compute_stability_metrics(df)
            csv_path, json_path = export_fitness_matrix(df, tag=params["tag"])

            try:
                base = os.path.basename(csv_path)
                if base.startswith("fitness_matrix_") and base.endswith(".csv"):
                    tag = base[len("fitness_matrix_") : -4]
                    fitness_dir = os.path.dirname(csv_path)
                    cfg_path = os.path.join(fitness_dir, f"fitness_config_{tag}.json")
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(params, f, indent=2)
            except Exception:
                pass

            self.after(
                0,
                lambda: self._on_scan_complete(
                    success=True, csv_path=csv_path, json_path=json_path
                ),
            )
        except Exception as exc:
            tb = traceback.format_exc()
            self.after(
                0,
                lambda: self._on_scan_complete(
                    success=False, error=str(exc), traceback_text=tb
                ),
            )

    def _on_scan_complete(
        self,
        success: bool,
        csv_path: Optional[str] = None,
        json_path: Optional[str] = None,
        error: Optional[str] = None,
        traceback_text: Optional[str] = None,
    ) -> None:
        self._is_running = False
        self.progress.stop()
        self.run_button.config(state=tk.NORMAL)

        if not success:
            msg = "Fitness scan failed."
            if error:
                msg += f"\n\nError: {error}"
            if traceback_text:
                msg += f"\n\nTraceback:\n{traceback_text}"
            messagebox.showerror("Fitness Scan", msg)
            return

        if csv_path:
            self._load_results_from_path(csv_path)
            self.notebook.select(self.results_frame)

    # ------------------------------------------------------------------
    # Results interactions
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        if self._full_df is None:
            return
        text = self.filter_var.get().strip().lower()
        if not text:
            self._current_df = self._full_df
            self._refresh_tree()
            return

        df = self._full_df
        mask = (
            df.get("asset", "").astype(str).str.lower().str.contains(text)
            | df.get("strategy_name", "").astype(str).str.lower().str.contains(text)
            | df.get("timeframe", "").astype(str).str.lower().str.contains(text)
        )
        self._current_df = df[mask].copy()
        self._refresh_tree()

    def _clear_filter(self) -> None:
        self.filter_var.set("")
        if self._full_df is not None:
            self._current_df = self._full_df
            self._refresh_tree()

    def _export_csv(self) -> None:
        if self._current_df is None or self._current_df.empty:
            messagebox.showinfo("Export CSV", "No data available to export.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Fitness View to CSV",
        )
        if not path:
            return

        df = self._current_df.drop(columns=["__row_id"], errors="ignore")
        try:
            df.to_csv(path, index=False)
            messagebox.showinfo("Export CSV", f"Exported CSV to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export CSV", f"Failed to export CSV:\n{exc}")

    def _export_json(self) -> None:
        if self._current_df is None or self._current_df.empty:
            messagebox.showinfo("Export JSON", "No data available to export.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Export Fitness View to JSON",
        )
        if not path:
            return

        df = self._current_df.drop(columns=["__row_id"], errors="ignore")
        try:
            df.to_json(path, orient="records", indent=2)
            messagebox.showinfo("Export JSON", f"Exported JSON to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export JSON", f"Failed to export JSON:\n{exc}")


    def _export_mapping(self) -> None:
        """Export Phase E best-config mapping file from the current fitness view."""
        if self._current_df is None or self._current_df.empty:
            messagebox.showinfo("Export Mapping", "No data available to export.")
            return

        rows = self._build_fitness_rows_for_mapping()
        if not rows:
            messagebox.showwarning(
                "Export Mapping",
                "Could not build any valid mapping records from the current data.",
            )
            return

        fitness_mapping_export.export_best_config_schema_dialog(
            parent=self,
            fitness_rows=rows,
        )

    def _build_fitness_rows_for_mapping(self) -> List[Dict[str, Any]]:
        """
        Build generic fitness rows from the current DataFrame suitable for
        core.asset_fitness_mapping.build_fitness_records_for_mapping.

        This method makes minimal assumptions about column names and uses
        _last_run_params for regime and risk_model fields. If certain
        expected metrics are missing, those rows will be skipped later by
        the core helper.
        """
        if self._current_df is None or self._current_df.empty:
            return []

        df = self._current_df.drop(columns=["__row_id"], errors="ignore")
        rows: List[Dict[str, Any]] = []

        params = self._last_run_params or {}
        regime = str(params.get("mode", "balanced"))

        # Base risk model derived from the GUI run parameters; additional
        # fields can be added in the future without changing Phase E.
        risk_model_base: Dict[str, Any] = {
            "position_pct": float(params.get("position_pct", 0.0)),
            "risk_pct": float(params.get("risk_pct", 0.0)),
        }
        reward_rr = params.get("reward_rr", None)
        if reward_rr is not None:
            try:
                risk_model_base["reward_rr_override"] = float(reward_rr)
            except (TypeError, ValueError):
                pass

        for _, row in df.iterrows():
            rd = row.to_dict()

            # Try several common column names for asset and timeframe so we
            # remain compatible with existing fitness exports.
            asset = (
                rd.get("asset")
                or rd.get("pair")
                or rd.get("symbol")
                or ""
            )
            asset = str(asset).strip()

            timeframe = (
                rd.get("timeframe")
                or rd.get("tf")
                or rd.get("time_frame")
                or ""
            )
            timeframe = str(timeframe).strip()

            raw_strategy_id = (
                rd.get("strategy_id")
                or rd.get("strategy_key")
                or rd.get("strategy")
            )
            raw_strategy_name = rd.get("strategy_name")

            if raw_strategy_id is not None and str(raw_strategy_id).strip():
                strategy_id = str(raw_strategy_id).strip()
            elif raw_strategy_name is not None and str(raw_strategy_name).strip():
                strategy_id = str(raw_strategy_name).strip()
            else:
                # Cannot determine a usable strategy id
                continue

            strategy_name = str(raw_strategy_name or strategy_id)

            if not asset or not timeframe or not strategy_id:
                continue

            fitness_row: Dict[str, Any] = {
                "asset": asset,
                "timeframe": timeframe,
                "regime": regime,
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "total_trades": rd.get("total_trades", rd.get("trades", 0)),
                "total_return_pct": rd.get("total_return_pct", rd.get("return_pct", 0.0)),
                "winrate_pct": rd.get("winrate_pct", rd.get("winrate", 0.0)),
                "expectancy_R": rd.get("expectancy_R", rd.get("expectancy", 0.0)),
                "max_dd_pct": rd.get("max_dd_pct", rd.get("max_drawdown_pct", 0.0)),
                "stability_score": rd.get("stability_score", 0.0),
                "risk_model": dict(risk_model_base),
            }

            rows.append(fitness_row)

        return rows

    # ------------------------------------------------------------------
    # Restoring / re-running
    # ------------------------------------------------------------------

    def _restore_run_params_from_dict(self, params: Dict[str, Any]) -> None:
        self._last_run_params = params

        self.strategy_listbox.selection_clear(0, tk.END)
        for i in range(self.strategy_listbox.size()):
            name = self.strategy_listbox.get(i)
            if name in params.get("strategies", []):
                self.strategy_listbox.selection_set(i)

        self.timeframe_listbox.selection_clear(0, tk.END)
        for i in range(self.timeframe_listbox.size()):
            tf = self.timeframe_listbox.get(i)
            if tf in params.get("timeframes", []):
                self.timeframe_listbox.selection_set(i)

        self.mode_var.set(params.get("mode", "balanced"))
        self.use_router_var.set(bool(params.get("use_router", False)))
        self.position_pct_var.set(float(params.get("position_pct", 15.0)))
        self.risk_pct_var.set(float(params.get("risk_pct", 1.0)))

        reward_rr = params.get("reward_rr", None)
        if reward_rr is None:
            self.use_default_rr_var.set(True)
        else:
            self.use_default_rr_var.set(False)
            self.rr_var.set(float(reward_rr))

        self.tag_var.set(params.get("tag", ""))

    def _on_rerun(self) -> None:
        if not self._last_run_params:
            messagebox.showinfo("Re-run Scan", "No previous run parameters available yet.")
            return

        self._restore_run_params_from_dict(self._last_run_params)
        self.notebook.select(self.run_frame)

    # ------------------------------------------------------------------
    # Tree sorting & double click
    # ------------------------------------------------------------------

    def _on_tree_heading_click(self, column: str) -> None:
        if self._current_df is None or self._current_df.empty:
            return

        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False

        df = self._current_df

        try:
            series = pd.to_numeric(df[column], errors="coerce")
            if series.notna().any():
                order = series.sort_values(ascending=self._sort_reverse).index
                self._current_df = df.loc[order].copy()
            else:
                raise ValueError
        except Exception:
            order = df[column].astype(str).sort_values(ascending=self._sort_reverse).index
            self._current_df = df.loc[order].copy()

        self._refresh_tree()

    def _on_tree_double_click(self, event: tk.Event) -> None:
        if self._full_df is None or self._full_df.empty:
            return

        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        try:
            row_id = int(item_id)
        except ValueError:
            return

        df = self._full_df
        match = df[df["__row_id"] == row_id]
        if match.empty:
            return

        row_data = match.iloc[0].to_dict()

        if self._detail_window is not None and self._detail_window.winfo_exists():
            self._detail_window.destroy()

        self._detail_window = FitnessDetailWindow(self, row_data=row_data, title="Fitness Row Details")
# gui/fitness_window.py v0.10 (932 lines)
