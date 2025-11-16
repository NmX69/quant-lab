# getdata.py
#
# GUI tool to download and normalize historical OHLCV data for one or more
# trading pairs using CryptoDataDownload Binance spot CSVs.
#
# - Input: trading pairs (comma separated), e.g. "BTCUSDT, ETHUSDT"
# - Input: interval (5m, 15m, 1h, 4h, 1d)
# - Input: history span (via dropdown; interval-aware)
# - Output: data/{SYMBOL}_{INTERVAL}.csv
#           with columns: timestamp, open, high, low, close, volume
# - Also maintains data/manifest.json with metadata about each dataset.

import os
import json
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

import pandas as pd
import requests

DATA_DIR = "data"
MANIFEST_FILE = os.path.join(DATA_DIR, "manifest.json")

# CryptoDataDownload URL pattern for Binance spot
# Example: https://www.cryptodatadownload.com/cdd/Binance_BTCUSDT_1h.csv
CDD_URL_TEMPLATE = "https://www.cryptodatadownload.com/cdd/Binance_{symbol}_{interval}.csv"

# Interval → [(label, max_days), ...]
# max_days = None means "all available"
PERIOD_OPTIONS = {
    "5m": [
        ("3 months", 90),
        ("6 months", 180),
        ("1 year", 365),
        ("All available", None),
    ],
    "15m": [
        ("6 months", 180),
        ("1 year", 365),
        ("2 years", 730),
        ("All available", None),
    ],
    "1h": [
        ("6 months", 180),
        ("1 year", 365),
        ("2 years", 730),
        ("4 years", 1460),
        ("All available", None),
    ],
    "4h": [
        ("1 year", 365),
        ("2 years", 730),
        ("4 years", 1460),
        ("All available", None),
    ],
    "1d": [
        ("2 years", 730),
        ("4 years", 1460),
        ("8 years", 2920),
        ("All available", None),
    ],
}


# ---------- Manifest helpers ----------

def load_manifest() -> dict:
    """Load manifest.json or create an empty structure if missing/invalid."""
    if not os.path.exists(MANIFEST_FILE):
        return {"version": 1, "pairs": {}}
    try:
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        return {"version": 1, "pairs": {}}
    if "pairs" not in m or not isinstance(m["pairs"], dict):
        m["pairs"] = {}
    if "version" not in m:
        m["version"] = 1
    return m


def save_manifest(m: dict) -> None:
    """Persist manifest.json."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, sort_keys=True)


def update_manifest(
    symbol: str,
    interval: str,
    source: str,
    filename: str,
    candles: int,
    ts_start: pd.Timestamp,
    ts_end: pd.Timestamp,
    history_span_days: int | None,
) -> None:
    """
    Upsert an entry in manifest.json for (symbol, interval).
    """
    m = load_manifest()
    pairs = m.setdefault("pairs", {})

    entry = pairs.setdefault(symbol, {})

    start_str = ts_start.isoformat().replace("+00:00", "Z") if hasattr(ts_start, "isoformat") else str(ts_start)
    end_str = ts_end.isoformat().replace("+00:00", "Z") if hasattr(ts_end, "isoformat") else str(ts_end)

    entry[interval] = {
        "symbol": symbol,
        "interval": interval,
        "source": source,
        "file": os.path.basename(filename),
        "candles": int(candles),
        "timestamp_start": start_str,
        "timestamp_end": end_str,
        "history_span_days": int(history_span_days) if history_span_days is not None else None,
        "downloaded_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }

    save_manifest(m)


# ---------- Logging ----------

def log_message(text_widget: ScrolledText, msg: str):
    """Append a message to the GUI log box."""
    text_widget.insert(tk.END, msg + "\n")
    text_widget.see(tk.END)
    text_widget.update_idletasks()


# ---------- Download + normalize ----------

def download_raw_csv(symbol: str, interval: str, log: ScrolledText) -> str:
    """
    Download raw CSV for given symbol/interval from CryptoDataDownload.
    Returns path to the temporary raw file.
    """
    url = CDD_URL_TEMPLATE.format(symbol=symbol, interval=interval)
    log_message(log, f"[{symbol} {interval}] Downloading from {url}")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"HTTP error: {e}")

    os.makedirs(DATA_DIR, exist_ok=True)
    raw_path = os.path.join(DATA_DIR, f"_raw_Binance_{symbol}_{interval}.csv")

    with open(raw_path, "wb") as f:
        f.write(resp.content)

    log_message(log, f"[{symbol} {interval}] Downloaded to {raw_path}")
    return raw_path


def _clean_col_name(col: str) -> str:
    """Normalize a column name: strip BOM/whitespace, lowercase."""
    if not isinstance(col, str):
        col = str(col)
    col = col.strip().lstrip("\ufeff").lower()
    return col


def _read_cdd_with_header_sniff(raw_path: str, log: ScrolledText) -> pd.DataFrame:
    """
    CryptoDataDownload sometimes has weird metadata rows before the header.
    Try several header rows until we find one containing 'date' or 'unix'.
    """
    for header_row in range(0, 10):
        try:
            df = pd.read_csv(raw_path, header=header_row)
        except Exception as e:
            log_message(log, f"  [debug] Failed reading with header={header_row}: {e}")
            continue

        cleaned_cols = [_clean_col_name(c) for c in df.columns]
        if any(c in ("date", "timestamp", "unix") for c in cleaned_cols):
            df.columns = cleaned_cols
            log_message(log, f"  [debug] Using header row {header_row}; columns={cleaned_cols}")
            return df

    # Fallback: comment-stripping approach
    try:
        df = pd.read_csv(raw_path, comment="#")
        cleaned_cols = [_clean_col_name(c) for c in df.columns]
        df.columns = cleaned_cols
        if any(c in ("date", "timestamp", "unix") for c in cleaned_cols):
            log_message(log, f"  [debug] Using comment-based header; columns={cleaned_cols}")
            return df
    except Exception as e:
        log_message(log, f"  [debug] Comment-based read failed: {e}")

    raise ValueError("No 'date'/'timestamp'/'unix' column found in raw CSV after header sniffing.")


def normalize_csv(
    raw_path: str,
    symbol: str,
    interval: str,
    max_days: int | None,
    log: ScrolledText,
) -> tuple[str, int, pd.Timestamp, pd.Timestamp]:
    """
    Normalize a CryptoDataDownload Binance CSV to:
      timestamp, open, high, low, close, volume

    Trim to last max_days of data (if not None).
    Save as data/{SYMBOL}_{INTERVAL}.csv and return:
      (out_path, candles, ts_start, ts_end)
    """
    log_message(log, f"[{symbol} {interval}] Normalizing data from {raw_path}")

    df = _read_cdd_with_header_sniff(raw_path, log)
    cols = list(df.columns)

    # Pick timestamp column
    ts_col = None
    for candidate in ("date", "timestamp", "unix"):
        if candidate in cols:
            ts_col = candidate
            break

    if ts_col is None:
        raise ValueError(f"No 'date'/'timestamp'/'unix' column found even after header sniffing. Columns: {cols}")

    # Parse timestamps
    if ts_col == "unix":
        df["timestamp"] = pd.to_datetime(df["unix"], unit="s", utc=True, errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")

    # Ensure OHLC are present
    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in cols:
            raise ValueError(f"Column '{col}' not found in normalized CSV. Columns: {cols}")

    # Volume: prefer 'volume', else 'volume btc', else 'volume usdt'
    vol_col = None
    if "volume" in cols:
        vol_col = "volume"
    elif "volume btc" in cols:
        vol_col = "volume btc"
    elif "volume usdt" in cols:
        vol_col = "volume usdt"
    else:
        raise ValueError(
            f"No volume column found (expected 'volume', 'volume btc', or 'volume usdt'). Columns: {cols}"
        )

    norm = df[["timestamp", "open", "high", "low", "close", vol_col]].copy()
    norm.rename(columns={vol_col: "volume"}, inplace=True)

    # Numeric conversion
    for col in ["open", "high", "low", "close", "volume"]:
        norm[col] = pd.to_numeric(norm[col], errors="coerce")

    norm = norm.dropna(subset=["timestamp", "close"])

    # Sort ascending, drop duplicate timestamps
    norm = norm.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Trim to last max_days (if specified)
    if max_days is not None and max_days > 0:
        cutoff = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc) - dt.timedelta(days=max_days)
        before = len(norm)
        norm = norm[norm["timestamp"] >= cutoff].reset_index(drop=True)
        after = len(norm)
        log_message(
            log,
            f"[{symbol} {interval}] Trimmed from {before} to {after} rows (last ~{max_days} days)",
        )

    if norm.empty:
        raise ValueError("No rows remain after normalization/trim; check history span or source data.")

    # Save normalized
    out_path = os.path.join(DATA_DIR, f"{symbol}_{interval}.csv")
    norm.to_csv(out_path, index=False)

    candles = len(norm)
    ts_start = norm["timestamp"].iloc[0]
    ts_end = norm["timestamp"].iloc[-1]

    log_message(
        log,
        f"[{symbol} {interval}] Normalized data saved to {out_path}\n"
        f"    Date range: {ts_start} -> {ts_end}\n"
        f"    Rows: {candles}",
    )

    return out_path, candles, ts_start, ts_end


def process_pairs(pairs_str: str, interval: str, max_days: int | None, log: ScrolledText):
    """Handle download → normalize → manifest update for multiple comma-separated pairs."""
    pairs = [p.strip().upper() for p in pairs_str.split(",") if p.strip()]
    if not pairs:
        messagebox.showerror("Error", "Please enter at least one trading pair.")
        return

    for symbol in pairs:
        # Basic sanity: must be alphanumeric
        if not symbol.isalnum():
            log_message(log, f"[{symbol}] Skipping: contains non-alphanumeric characters.")
            continue

        raw_path = None
        try:
            raw_path = download_raw_csv(symbol, interval, log)
            out_path, candles, ts_start, ts_end = normalize_csv(raw_path, symbol, interval, max_days, log)

            history_span_days = max_days
            source = "CryptoDataDownload:Binance"

            # Update manifest.json
            update_manifest(symbol, interval, source, out_path, candles, ts_start, ts_end, history_span_days)

        except Exception as e:
            log_message(log, f"[{symbol} {interval}] ERROR: {e}")
        finally:
            # Remove raw file if it exists
            try:
                if raw_path and os.path.exists(raw_path):
                    os.remove(raw_path)
            except Exception:
                pass


# ---------- GUI ----------

def build_gui():
    root = tk.Tk()
    root.title("Crypto Data Downloader (Binance via CryptoDataDownload)")
    root.geometry("700x450")

    main_frame = ttk.Frame(root, padding=10)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Trading pairs input
    ttk.Label(main_frame, text="Trading pairs (comma-separated):").grid(row=0, column=0, sticky="w")
    pairs_entry = ttk.Entry(main_frame, width=60)
    pairs_entry.grid(row=0, column=1, sticky="we", padx=5)
    pairs_entry.insert(0, "BTCUSDT")

    # Interval selector
    ttk.Label(main_frame, text="Interval:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    interval_var = tk.StringVar(value="1h")
    interval_combo = ttk.Combobox(
        main_frame,
        textvariable=interval_var,
        values=["5m", "15m", "1h", "4h", "1d"],
        width=10,
        state="readonly",
    )
    interval_combo.grid(row=1, column=1, sticky="w", padx=5, pady=(8, 0))

    # History span selector (dropdown)
    ttk.Label(main_frame, text="History span:").grid(row=2, column=0, sticky="w", pady=(8, 0))
    period_var = tk.StringVar()
    period_combo = ttk.Combobox(
        main_frame,
        textvariable=period_var,
        values=[],
        width=20,
        state="readonly",
    )
    period_combo.grid(row=2, column=1, sticky="w", padx=5, pady=(8, 0))

    # Log box
    log_label = ttk.Label(main_frame, text="Log:")
    log_label.grid(row=3, column=0, sticky="nw", pady=(10, 0))
    log_box = ScrolledText(main_frame, width=80, height=16)
    log_box.grid(row=3, column=1, sticky="nsew", padx=5, pady=(10, 0))

    main_frame.rowconfigure(3, weight=1)
    main_frame.columnconfigure(1, weight=1)

    def update_period_options(*_args):
        """Update the history-span dropdown when interval changes."""
        interval = interval_var.get()
        options = PERIOD_OPTIONS.get(interval, PERIOD_OPTIONS["1h"])
        labels = [label for (label, _days) in options]
        period_combo["values"] = labels
        # Default: second option if it exists, else first
        if labels:
            default_label = labels[1] if len(labels) > 1 else labels[0]
            period_var.set(default_label)

    # Initialize period options for default interval
    update_period_options()
    interval_var.trace_add("write", update_period_options)

    def on_download():
        pairs_str = pairs_entry.get().strip()
        interval = interval_var.get()
        period_label = period_var.get()

        options = PERIOD_OPTIONS.get(interval, PERIOD_OPTIONS["1h"])
        label_to_days = {label: days for (label, days) in options}
        max_days = label_to_days.get(period_label, None)

        log_box.delete("1.0", tk.END)
        log_message(
            log_box,
            f"Starting download for pairs: {pairs_str} | Interval: {interval} | History: {period_label}",
        )
        process_pairs(pairs_str, interval, max_days, log_box)
        log_message(log_box, "Done.")

    download_btn = ttk.Button(main_frame, text="Download Data", command=on_download)
    download_btn.grid(row=4, column=1, sticky="e", pady=(10, 0))

    root.mainloop()


if __name__ == "__main__":
    build_gui()
