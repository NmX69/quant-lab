# quant_lab.py
# Purpose: Canonical Quant-Lab entrypoint (currently launches the backtester GUI).
# Major External Functions/Classes: BacktesterGUI
# Notes: Backwards-compatible with backtester.py which can simply import and call main().

import tkinter as tk
from gui.backtester_gui import BacktesterGUI


def main() -> None:
    root = tk.Tk()
    app = BacktesterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

# quant_lab.py v0.1 (19 lines)
