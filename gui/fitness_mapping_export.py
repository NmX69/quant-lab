# gui/fitness_mapping_export.py
# Purpose: GUI helpers to export Phase E best-config mapping files from fitness results.
# API's: export_best_config_schema_dialog
# Notes: Intended to be called from FitnessTabbedWindow in gui/fitness_window.py.

"""GUI helpers for exporting Phase E mapping files from the fitness window.

This module does not own the fitness computation; it only provides a small
dialog-oriented workflow that other GUI components (e.g. FitnessTabbedWindow)
can call once they have in-memory fitness results.

Expected usage from gui/fitness_window.py (conceptual):

    from gui import fitness_mapping_export

    class FitnessTabbedWindow(tk.Toplevel):
        def __init__(...):
            ...
            self._last_fitness_rows = None  # whatever structure your Phase D code returns
            export_btn = ttk.Button(
                self.results_tab,
                text="Export Best-Config Schema",
                command=self._on_export_best_config_clicked,
            )
            export_btn.grid(...)

        def _on_export_best_config_clicked(self):
            if not self._last_fitness_rows:
                messagebox.showinfo("Export Mapping", "Run a fitness job before exporting.")
                return
            fitness_mapping_export.export_best_config_schema_dialog(
                parent=self,
                fitness_rows=self._last_fitness_rows,
            )

This keeps Phase E GUI wiring isolated and avoids assumptions about how
FitnessTabbedWindow is structured internally.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from typing import Any, Iterable, Mapping, Sequence

from core import asset_fitness_mapping, mapping_generator


FitnessRow = Mapping[str, Any]


def export_best_config_schema_dialog(
    parent: tk.Tk | tk.Toplevel,
    fitness_rows: Iterable[FitnessRow],
) -> None:
    """Run an interactive export of a best-config mapping file.

    Parameters
    ----------
    parent:
        The parent window (typically FitnessTabbedWindow). Used as the
        owner for dialogs.

    fitness_rows:
        Iterable of dict-like rows representing fitness results. The
        caller is responsible for providing rows with the keys expected
        by `core.asset_fitness_mapping.build_fitness_records_for_mapping`.
    """
    rows_list: Sequence[FitnessRow] = list(fitness_rows)
    if not rows_list:
        messagebox.showinfo("Export Mapping", "No fitness data available to export.", parent=parent)
        return

    # Optional: ask user for a tag and description
    tag = simpledialog.askstring(
        "Export Mapping",
        "Optional tag for this mapping file (e.g. btc_eth_1h):",
        parent=parent,
    )
    if tag is None:
        # User cancelled
        return

    description = simpledialog.askstring(
        "Export Mapping",
        "Optional description for this mapping run:",
        parent=parent,
    )
    if description is None:
        description = ""

    # Optional: choose directory (defaults to ./results if cancelled)
    initial_dir = os.path.abspath("results")
    target_dir = filedialog.askdirectory(
        parent=parent,
        title="Choose directory to save mapping file",
        initialdir=initial_dir,
    )
    if not target_dir:
        target_dir = "results"

    # Build fitness_records from generic rows
    # Note: if you want hellmoon_compatible=True by default, change the flag here.
    fitness_records = asset_fitness_mapping.build_fitness_records_for_mapping(
        rows_list,
        source_id="fitness_gui_session",
        hellmoon_compatible=None,
    )

    if not fitness_records:
        messagebox.showwarning(
            "Export Mapping",
            "Could not build any valid records from fitness data; nothing exported.",
            parent=parent,
        )
        return

    mapping_set = mapping_generator.build_mapping_set(
        fitness_records,
        sdl_schema_version="1.0",
        generated_from="fitness_gui_session",
        description=description or "",
    )

    try:
        path = mapping_generator.save_mapping_set(
            mapping_set,
            tag=tag or None,
            base_dir=target_dir,
        )
    except Exception as exc:
        messagebox.showerror(
            "Export Mapping",
            f"Failed to save mapping file:\n{exc}",
            parent=parent,
        )
        return

    messagebox.showinfo(
        "Export Mapping",
        f"Best-config mapping exported to:\n{os.path.abspath(path)}",
        parent=parent,
    )
# gui/fitness_mapping_export.py v0.1 (145 lines)
