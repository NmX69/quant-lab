# Strategy Definition Language (SDL)

> **Version**: 1.0  
> **Purpose**: Define trading strategies in **pure JSON** — no Python code required.  
> **Location**: `strategies/*.json`  
> **Engine**: `core/strategy_loader.py` loads and validates.

---

## Why SDL?

- **No code changes** → Add new strategies in 30 seconds  
- **LLM-friendly** → Grok/ChatGPT can generate strategies  
- **Backtester is an interpreter** → Same engine, infinite strategies  
- **Future-proof** → Add filters, risk models, multi-timeframe later

---

## Schema

```json
{
  "name": "string",
  "regime": "trending" | "ranging" | "both",
  "direction": "long" | "short" | "both",

  "entry": {
    "conditions": [ ... ]
  },

  "exit": {
    "stop_loss": number | "mode_stop",
    "take_profit": number | "mode_tp",
    "partial_exit": number,
    "signal_exit": [ ... ],
    "trailing_stop": number
  },

  "risk": {
    "sizing": "fixed_usd" | "equity_pct" | "atr",
    "max_exposure_usd": number,
    "risk_per_trade_pct": number,
    "atr_multiplier": number
  },

  "filters": [ ... ]
}


FIELD REFERENCE
Field,Type,Required,Description
name,string,Yes,Human name in GUI
regime,string,Yes,When strategy runs
direction,string,Yes,Long/short/both
entry.conditions[],array,Yes,All must be true
exit.stop_loss,number/string,Yes,"""mode_stop"" = use mode"
exit.take_profit,number/string,Yes,"""mode_tp"" = use mode"
exit.partial_exit,number,No,0.0–1.0
exit.signal_exit[],array,No,Any one triggers exit
exit.trailing_stop,number,No,% from peak
risk.sizing,string,Yes,Position sizing method
risk.max_exposure_usd,number,No,For fixed_usd
risk.risk_per_trade_pct,number,No,For equity_pct
risk.atr_multiplier,number,No,For atr
filters[],array,No,Must pass before entry

ENTRY CONDITIONS
Type,Parameters,Meaning
macd_cross,"""direction"": ""up"" or ""down""",MACD crosses signal
adx,"""above"": 25 or ""mode_threshold""",ADX strength
rsi,"""below"": 30, ""above"": 70",Overbought/oversold
price_above_ema,"""period"": 150",Price > EMA
price_below_bb,"""std"": 2.0",Price < lower band
price_above_bb,"""std"": 2.0",Price > upper band

EXIT SIGNALS
Type,Meaning
"macd_cross + ""down""",MACD crosses below signal
price_crosses_mid_bb,Price crosses BB middle

RISK MODELS
Mode,How It Works
fixed_usd,$15 per trade
equity_pct,1% of current equity
atr,Risk = 1% → Stop = N × ATR → Size = Risk / Stop

EXAMPLES
{
  "name": "Trend MACD+ADX",
  "regime": "trending",
  "direction": "long",
  "entry": {
    "conditions": [
      { "type": "macd_cross", "direction": "up" },
      { "type": "adx", "above": "mode_threshold" },
      { "type": "price_above_ema", "period": 150 }
    ]
  },
  "exit": {
    "stop_loss": "mode_stop",
    "take_profit": "mode_tp",
    "partial_exit": 0.5,
    "signal_exit": [
      { "type": "macd_cross", "direction": "down" }
    ]
  },
  "risk": {
    "sizing": "fixed_usd",
    "max_exposure_usd": 15.0
  }
}


How to Add a New Strategy

Copy an existing .json
Edit name, regime, entry, exit
Save as new_strategy.json
Run backtester → appears in dropdown


Engine Integration

core/strategy_loader.py → loads all .json
GUI → shows name in dropdown
Engine → interprets conditions at runtime


SDL = Strategy as Data
No Python. No Recompile. No Risk.
