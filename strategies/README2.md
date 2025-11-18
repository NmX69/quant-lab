Yeah, a README is the right answer here. Let’s design it so you can hand this to “future you” and they can write a strategy JSON from scratch without guessing.

Below is something you can literally drop into `strategies/README.md` and tweak later. It:

* Lists **all core fields** for risk/position/regimes.
* Marks **required vs optional**.
* Gives **allowed values** and **sane defaults**.
* Ends with a **full template** containing every field, with “disabled” values where appropriate.

---

````markdown
# Strategy JSON Spec

This document explains how to write a strategy JSON file for the backtester.

The goal: you can create or edit a strategy file **without asking the AI** and know:
- Which fields are **required**.
- What each field **does**.
- What values are **allowed**.
- How **regime overrides** and **GUI defaults** interact.

---

## 1. Precedence Rules (who overrides whom?)

For ANY setting that can exist in multiple places:

1. **GUI defaults** (sliders in the backtester) – lowest priority.
2. **Strategy JSON base** – overrides GUI for this specific strategy.
3. **Strategy JSON `regime_overrides`** – highest priority (per regime).

So effectively:

> `GUI < strategy base < strategy.regime_overrides[regime]`

If a value is:
- **Missing everywhere** → you get the engine’s hard-coded default (if any).
- **Present in base JSON only** → used in all regimes.
- **Present in `regime_overrides` for the current regime** → that value wins.

---

## 2. Supported regimes

The engine currently recognizes these regime names:

- `"trending_up"`
- `"trending_down"`
- `"ranging"`

You **don’t have to** override all of them. Only define the ones you care about under `"regime_overrides"`.

---

## 3. Top-Level Structure

Every strategy JSON is a single object with:

- A **base configuration** (applies to all regimes by default).
- An optional `"regime_overrides"` section.

High level:

```json
{
  "name": "...",
  "description": "...",
  "symbol": "...",
  "timeframe": "...",
  "enabled": true,

  "position": { ... },
  "risk": { ... },
  "fees": { ... },

  "regime_overrides": {
    "trending_up": { ... },
    "trending_down": { ... },
    "ranging": { ... }
  },

  "entry_rules": [ ... ],
  "exit_rules": [ ... ],
  "filters": [ ... ]
}
````

You can safely ignore `entry_rules`, `exit_rules`, and `filters` for now if you’re only messing with risk/position sizing; they are there for signal logic.

---

## 4. Required Fields (minimal strategy)

These are the fields you should ALWAYS set in each file:

### 4.1 `name` (required)

* **Type:** string
* **Example:** `"btc_mean_revert"`
* **Meaning:** Internal name for this strategy.

### 4.2 `symbol` (required)

* **Type:** string
* **Example:** `"BTCUSDT"`
* **Meaning:** Trading symbol this strategy is designed for.

### 4.3 `timeframe` (required)

* **Type:** string
* **Example:** `"1h"`, `"4h"`, `"15m"`
* **Meaning:** Candle timeframe.

### 4.4 `position` (required block)

Defines how big each trade is.

```json
"position": {
  "mode": "equity_pct",
  "equity_pct": 15.0,
  "fixed_size": null
}
```

* **`mode`** (required)

  * Type: string
  * Allowed values:

    * `"equity_pct"` – position size is a **percentage of current equity**.
    * `"fixed_size"` – position size is a fixed notional (in quote currency).
* **`equity_pct`** (required if `mode == "equity_pct"`)

  * Type: number (float)
  * Example: `15.0` → 15% of current equity.
  * Effective range: `1.0` to `100.0` is sane.
* **`fixed_size`** (required if `mode == "fixed_size"`)

  * Type: number or `null`
  * Example: `100.0` → trade size is always 100 USDT notional.
  * Use `null` to “disable” it for `equity_pct` mode.

For your mental model:

* Equity = 100 USDT
* `mode = "equity_pct"`, `equity_pct = 15.0` → position notional = 15 USDT.

### 4.5 `risk` (required block for SL/TP)

```json
"risk": {
  "risk_pct": 1.0,
  "rr": 1.5,
  "trailing_stop_pct": 0.0
}
```

* **`risk_pct`** (required)

  * Type: number (float)
  * Meaning: **% of current equity you are willing to lose** if SL hits.
  * Example: equity = 100, `risk_pct = 1.0` → max loss = 1 USDT.
* **`rr`** (required)

  * Type: number (float)
  * Meaning: risk–reward multiple.
  * Example: `rr = 1.5` → TP is 1.5× further from entry than SL (in equity terms).
* **`trailing_stop_pct`** (required but can be 0 to disable)

  * Type: number (float)
  * Meaning: percent trail from **best favorable price**.
  * Example: `0.0` → no trailing stop; `0.05` → 5% trailing stop.

This matches your intended behavior:

* Equity = 100
* `equity_pct = 15.0` → position = 15 USDT
* `risk_pct = 1.0` → max loss = 1 USDT
* `rr = 1.5` → target profit = 1.5 USDT

The engine derives SL distance and TP distance from those numbers.

---

## 5. Optional Fields (with recommended defaults)

### 5.1 `description` (optional but recommended)

* **Type:** string
* Example: `"Mean reversion on BTCUSDT 1h"`

If missing: engine just doesn’t display a description.

### 5.2 `enabled` (optional)

* **Type:** boolean
* Default if omitted: `true`
* Purpose: allow you to “turn off” a strategy without deleting its file.

### 5.3 `fees` (optional for now)

```json
"fees": {
  "taker_fee_pct": 0.1,
  "maker_fee_pct": 0.1
}
```

* **`taker_fee_pct`**

  * Type: number (float)
  * Meaning: percent per side as the exchange’s taker fee.
  * Example: `0.1` = 0.1% (Binance spot-like).
* **`maker_fee_pct`**

  * Type: number (float)
  * Currently not heavily used; you can mirror `taker_fee_pct`.

If you omit `fees`, the engine should fall back to defaults (you can standardize on 0.1% per side).

### 5.4 `entry_rules`, `exit_rules`, `filters` (optional for now)

These drive the **actual signal logic**. They can be arrays of rule objects. Until we document them fully, you can:

* Leave them as `[]` (empty arrays) and rely on hard-coded strategies, or
* Copy from an existing working strategy and slightly tweak.

We can do a separate README section later just for rule syntax once we freeze it.

---

## 6. Regime Overrides

`"regime_overrides"` lets you change **any** of the main blocks **per regime**:

```json
"regime_overrides": {
  "trending_up": {
    "position": {
      "mode": "equity_pct",
      "equity_pct": 20.0,
      "fixed_size": null
    },
    "risk": {
      "risk_pct": 0.75,
      "rr": 2.0,
      "trailing_stop_pct": 0.05
    }
  },

  "ranging": {
    "position": {
      "mode": "equity_pct",
      "equity_pct": 15.0,
      "fixed_size": null
    },
    "risk": {
      "risk_pct": 1.5,
      "rr": 1.0,
      "trailing_stop_pct": 0.0
    }
  }
}
```

Rules:

* Everything inside a regime (e.g. `"ranging"`) is **merged** with the base.
* Values present in regime override values from base.
* Values not present in regime fall back to base.

Example:

* Base `risk_pct = 1.0`.
* `trending_up.risk.risk_pct = 0.75`.
* In trending_up → you risk 0.75%.
* In trending_down (no override) → still 1.0%.

You do **not** have to repeat every field in each regime; only the ones you want to tweak.

---

## 7. Full Template Strategy (all fields + disabled options)

Below is a **maximal template** including everything we’ve discussed.
You can copy this and edit values.

This is **pseudo-JSON with comments**—do NOT paste comments into real `.json` files.

```jsonc
{
  // === BASIC INFO ===
  "name": "TEMPLATE_STRATEGY",          // REQUIRED: internal name
  "description": "Describe what this strategy does",  // optional
  "symbol": "BTCUSDT",                  // REQUIRED
  "timeframe": "1h",                    // REQUIRED ("1h", "4h", "15m", etc.)
  "enabled": true,                      // optional (default true)

  // === POSITION SIZING ===
  "position": {
    // REQUIRED: how to determine trade size
    // "equity_pct" -> position size = equity * (equity_pct / 100)
    // "fixed_size" -> position size = fixed_size (quote currency)
    "mode": "equity_pct",

    // REQUIRED if mode == "equity_pct"
    "equity_pct": 15.0,      // 15% of current equity

    // REQUIRED if mode == "fixed_size"; set to null when not used
    "fixed_size": null
  },

  // === RISK & REWARD ===
  "risk": {
    // REQUIRED: max loss per trade as % of equity
    "risk_pct": 1.0,              // 1% of equity

    // REQUIRED: take-profit multiple of risk
    "rr": 1.5,                    // 1.5R reward

    // REQUIRED but can be 0 to disable
    // If > 0: trailing stop as % from best favorable price
    "trailing_stop_pct": 0.0      // 0.0 = no trailing stop
  },

  // === FEES (OPTIONAL) ===
  "fees": {
    // Exchange taker fee per side (in %)
    "taker_fee_pct": 0.1,         // 0.1% per side

    // Exchange maker fee per side (in %)
    "maker_fee_pct": 0.1          // usually same as taker or slightly lower
  },

  // === ENTRY RULES (OPTIONAL – PLACEHOLDER) ===
  "entry_rules": [
    // Example (NOT real code, just a placeholder):
    // {
    //   "type": "indicator_cross",
    //   "indicator_fast": "ema_20",
    //   "indicator_slow": "ema_50",
    //   "direction": "above"
    // }
  ],

  // === EXIT RULES (OPTIONAL – PLACEHOLDER) ===
  "exit_rules": [
    // Example:
    // {
    //   "type": "indicator_cross",
    //   "indicator_fast": "ema_20",
    //   "indicator_slow": "ema_50",
    //   "direction": "below"
    // }
  ],

  // === EXTRA FILTERS (OPTIONAL – PLACEHOLDER) ===
  "filters": [
    // Example:
    // { "type": "min_volume", "value": 100000 }
  ],

  // === REGIME OVERRIDES (OPTIONAL) ===
  "regime_overrides": {
    // TRENDING UP: take more aggressive position, tighter risk, higher RR, trailing stop on
    "trending_up": {
      "position": {
        "mode": "equity_pct",
        "equity_pct": 20.0,
        "fixed_size": null
      },
      "risk": {
        "risk_pct": 0.75,
        "rr": 2.0,
        "trailing_stop_pct": 0.05
      }
    },

    // RANGING: smaller RR, maybe more risk
    "ranging": {
      "position": {
        "mode": "equity_pct",
        "equity_pct": 15.0,
        "fixed_size": null
      },
      "risk": {
        "risk_pct": 1.5,
        "rr": 1.0,
        "trailing_stop_pct": 0.0
      }
    }

    // "trending_down": { ... }   // Add if you want special behavior there
  }
}
```

---

If you want, next step I can:

* Take **one of your existing actual strategy JSONs**,
* Rewrite it to match this spec,
* And annotate which parts are currently used vs ignored by the engine.
