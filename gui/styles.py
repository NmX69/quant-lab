# gui/styles.py
# Purpose: Centralize ttk style configuration for the Quant-Lab GUI.
# Major External Functions/Classes: setup_styles
# Notes: Uses the default Tk root; call once early in GUI initialization.

import tkinter as tk
from tkinter import ttk


def setup_styles() -> None:
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        ".",
        background="#0d1117",
        foreground="#c9d1d9",
        font=("Consolas", 16),
    )
    style.configure(
        "TLabel",
        background="#0d1117",
        foreground="#58a6ff",
        font=("Consolas", 16, "bold"),
    )
    style.configure("TButton", padding=8, font=("Consolas", 16, "bold"))
    style.map(
        "TButton",
        background=[("active", "#238636")],
        foreground=[("active", "white")],
    )
    style.configure(
        "TCombobox",
        fieldbackground="white",
        background="white",
        foreground="black",
        font=("Consolas", 16),
    )
    style.map("TCombobox", fieldbackground=[("readonly", "white")])
    style.configure(
        "TEntry",
        fieldbackground="white",
        background="white",
        foreground="black",
        font=("Consolas", 16),
    )
    style.configure(
        "TCheckbutton",
        background="#0d1117",
        foreground="#c9d1d9",
        font=("Consolas", 16),
    )

# gui/styles.py v0.1 (53 lines)
