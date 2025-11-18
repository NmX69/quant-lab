Nice, this is a clean little strategy. I’ll do exactly what we talked about:

1. **Interpret your existing JSON.**
2. **Convert it into the new “full spec” format** (with comments).
3. **Explain how each old field maps to the new structure.**

> ⚠️ The JSON below uses `//` comments, so it’s **JSONC** for documentation.
> For real `.json` files you’ll need to **remove all comments**.

---

## 1. Rewritten strategy in the new spec

Assumptions I’m making (you can tweak them):

* Symbol / timeframe are unknown → I’ll set placeholders: `"BTCUSDT"`, `"1h"`.
* You didn’t specify position size, so I’ll default to **15% equity** (`equity_pct = 15.0`) which matches what you’ve been asking for.
* Your old **3% SL / 9% TP** is effectively **3R** (9 / 3 = 3) → I’ll encode that as `risk_pct = 1.0`, `rr = 3.0`.
* Regime is `ranging` only → we put the special behavior inside `regime_overrides.ranging`.

```jsonc
{
  // === BASIC INFO ===
  "name": "range_rsi_bb",                     // from your original
  "description": "Range strategy: RSI + Bollinger Bands in ranging regime",
  "symbol": "BTCUSDT",                        // TODO: set correctly
  "timeframe": "1h",                          // TODO: set correctly
  "enabled": true,

  // === POSITION SIZING ===
  // You had: "risk": { "sizing": "equity_pct", ... } → means we use equity % sizing.
  "position": {
    "mode": "equity_pct",                     // from risk.sizing = "equity_pct"
    "equity_pct": 15.0,                       // <-- CHOSEN DEFAULT, adjust in GUI or here
    "fixed_size": null
  },

  // === RISK & REWARD ===
  // You had:
  //   "exit": { "stop_loss": "3%", "take_profit": "9%" }
  //   "risk": { "risk_per_trade_pct": 1.0 }
  //
  // That implies:
  //   - You risk 1% of equity per trade
  //   - Your reward is 3× that distance (9% vs 3%), so RR = 3.0
  "risk": {
    "risk_pct": 1.0,                          // from risk_per_trade_pct
    "rr": 3.0,                                // derived from 3% SL / 9% TP = 3R
    "trailing_stop_pct": 0.0                  // no trailing stop in your original
  },

  // === FEES (DEFAULT BINANCE-LIKE) ===
  "fees": {
    "taker_fee_pct": 0.1,
    "maker_fee_pct": 0.1
  },

  // === ENTRY RULES ===
  // From:
  //   "entry": {
  //     "conditions": [
  //       {"type": "price_near_bb_lower"},
  //       {"type": "rsi", "below": 30}
  //     ]
  //   }
  //
  // I’m encoding this as high-level conditions; your engine can interpret
  // these however we decide in the “rules” spec.
  "entry_rules": [
    {
      "type": "price_near_bb_lower"           // price near lower Bollinger Band
    },
    {
      "type": "rsi",
      "below": 30                             // RSI below 30
    }
  ],

  // === EXIT RULES ===
  // Original:
  //   "exit": {
  //     "stop_loss": "3%",
  //     "take_profit": "9%",
  //     "signal_exit": [ { "type": "price_crosses_mid_bb" } ]
  //   }
  //
  // The price-based SL/TP is now expressed structurally via risk_pct + rr.
  // We still keep the signal-based exit as a rule:
  "exit_rules": [
    {
      "type": "signal_exit",
      "conditions": [
        {
          "type": "price_crosses_mid_bb"
        }
      ]
    }
  ],

  // === FILTERS / DIRECTION ===
  // You had: "direction": "both"
  // We can represent this as a filter allowing both long and short.
  "filters": [
    {
      "type": "direction",
      "value": "both"                         // "long" | "short" | "both"
    }
  ],

  // === REGIME OVERRIDES ===
  // You had: "regime": "ranging"
  //
  // This strategy is *meant* specifically for ranging regimes, so:
  // - Base config is generic
  // - Under "ranging", we can confirm or tweak the risk/position if desired
  "regime_overrides": {
    "ranging": {
      "position": {
        "mode": "equity_pct",
        "equity_pct": 15.0,                   // you can make ranging-specific tweaks here
        "fixed_size": null
      },
      "risk": {
        "risk_pct": 1.0,
        "rr": 3.0,
        "trailing_stop_pct": 0.0
      }
    }
  }
}
```

---

## 2. Field-by-field mapping from your original

Here’s how your original JSON mapped into this spec:

### Top-level

* `"name": "range_rsi_bb"` → same.
* `"regime": "ranging"` → migrated into `regime_overrides.ranging`.
* `"direction": "both"` → represented as a `filters` rule: `{ "type": "direction", "value": "both" }`.

### `entry`

Original:

```json
"entry": {
  "conditions": [
    {"type": "price_near_bb_lower"},
    {"type": "rsi", "below": 30}
  ]
}
```

Mapped to:

```jsonc
"entry_rules": [
  { "type": "price_near_bb_lower" },
  { "type": "rsi", "below": 30 }
]
```

Same semantics; just normalized into the `"entry_rules"` array.

### `exit`

Original:

```json
"exit": {
  "stop_loss": "3%",
  "take_profit": "9%",
  "signal_exit": [
    {"type": "price_crosses_mid_bb"}
  ]
}
```

* The **fixed 3% and 9% price stops** are now encoded conceptually as:

  * `risk.risk_pct = 1.0`
  * `risk.rr = 3.0`
* The **signal-based exit** is preserved:

```jsonc
"exit_rules": [
  {
    "type": "signal_exit",
    "conditions": [
      { "type": "price_crosses_mid_bb" }
    ]
  }
]
```

### `risk`

Original:

```json
"risk": {
  "sizing": "equity_pct",
  "risk_per_trade_pct": 1.0
}
```

Mapped to:

```jsonc
"position": {
  "mode": "equity_pct",      // from sizing
  "equity_pct": 15.0,        // chosen engine/GUI default
  "fixed_size": null
},
"risk": {
  "risk_pct": 1.0,           // from risk_per_trade_pct
  "rr": 3.0,                 // derived from 3%/9% exits
  "trailing_stop_pct": 0.0
}
```

---

## 3. What you can edit and experiment with

For this strategy specifically, the “knobs” you’d likely tweak:

* **Position sizing**

  * `position.mode`: `"equity_pct"` vs `"fixed_size"`.
  * `position.equity_pct`: 5–25 range is sane for backtests; 15 is what you asked for.

* **Risk-per-trade**

  * `risk.risk_pct`: try values from `0.25` to `2.0`.

* **Reward multiple**

  * `risk.rr`: you effectively chose 3.0; you can explore 1.0, 1.5, 2.0, 3.0, etc.

* **Regime overrides**

  * Under `"regime_overrides".ranging`, you can tighten or loosen risk/size without touching other regimes.

---

If you send me one more real strategy JSON from your existing set, I can:

* Convert it to this same format,
* Then we can turn this into the **canonical example** in your `strategies/README.md` so you have a clear pattern to copy for new strategies.
