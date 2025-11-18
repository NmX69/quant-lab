# core/indicators.py
# PHASE 6: ADDED EMA_50, STOCHASTIC, ATR

import pandas as pd

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
EMA_TREND_PERIOD = 150
EMA_FAST_CROSS = 50  # For ema_cross strategies
SMA_REGIME_PERIOD = 50
ADX_PERIOD = 14
ADX_TRENDING = 25
ADX_RANGING = 20
REGIME_MIN_DURATION = 5
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0
VOLUME_LOOKBACK = 20
STOCH_K_PERIOD = 14
STOCH_D_PERIOD = 3
ATR_PERIOD = 14


def add_indicators_and_regime(df: pd.DataFrame, adx_period: int = ADX_PERIOD) -> pd.DataFrame:
    if df.empty:
        return df

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # MACD
    df["ema_fast"] = close.ewm(span=MACD_FAST, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=MACD_SLOW, adjust=False).mean()
    df["macd"] = df["ema_fast"] - df["ema_slow"]
    df["signal"] = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()

    # EMAs for cross and trend
    df["ema_50"] = close.ewm(span=EMA_FAST_CROSS, adjust=False).mean()
    df["ema_150"] = close.ewm(span=EMA_TREND_PERIOD, adjust=False).mean()

    # SMA 50
    df["sma_50"] = close.rolling(SMA_REGIME_PERIOD).mean()

    # ADX, +DI, -DI
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    tr_smooth = tr.ewm(alpha=1/adx_period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/adx_period, adjust=False).mean() / (tr_smooth + 1e-8)
    minus_di = 100 * minus_dm.ewm(alpha=1/adx_period, adjust=False).mean() / (tr_smooth + 1e-8)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-8)
    df["adx"] = dx.ewm(alpha=1/adx_period, adjust=False).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(span=RSI_PERIOD, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(span=RSI_PERIOD, adjust=False).mean()
    rs = gain / (loss + 1e-8)
    df["rsi"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df["bb_mid"] = close.rolling(BB_PERIOD).mean()
    bb_std = close.rolling(BB_PERIOD).std()
    df["bb_upper"] = df["bb_mid"] + BB_STD * bb_std
    df["bb_lower"] = df["bb_mid"] - BB_STD * bb_std

    # Volume Z-Score
    vol_mean = volume.rolling(VOLUME_LOOKBACK).mean()
    vol_std = volume.rolling(VOLUME_LOOKBACK).std()
    df["volume_zscore"] = (volume - vol_mean) / (vol_std + 1e-8)

    # Stochastic Oscillator
    low_min = low.rolling(STOCH_K_PERIOD).min()
    high_max = high.rolling(STOCH_K_PERIOD).max()
    df["stoch_k"] = 100 * (close - low_min) / (high_max - low_min + 1e-8)
    df["stoch_d"] = df["stoch_k"].rolling(STOCH_D_PERIOD).mean()

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    # Regime Detection
    df["raw_trending_up"] = (df["adx"] > ADX_TRENDING) & (df["plus_di"] > df["minus_di"]) & (close > df["sma_50"])
    df["raw_trending_down"] = (df["adx"] > ADX_TRENDING) & (df["minus_di"] > df["plus_di"]) & (close < df["sma_50"])
    df["raw_ranging"] = (df["adx"] < ADX_RANGING) | (~df["raw_trending_up"] & ~df["raw_trending_down"])

    df["trending_up"] = False
    df["trending_down"] = False
    df["ranging"] = False

    current_regime = None
    regime_start = 0
    for i in range(len(df)):
        if df["raw_trending_up"].iloc[i]:
            new_regime = "trending_up"
        elif df["raw_trending_down"].iloc[i]:
            new_regime = "trending_down"
        else:
            new_regime = "ranging"

        if new_regime != current_regime:
            if current_regime and i - regime_start >= REGIME_MIN_DURATION:
                df.loc[regime_start:i, current_regime] = True
            regime_start = i
            current_regime = new_regime

    if current_regime and len(df) - regime_start >= REGIME_MIN_DURATION:
        df.loc[regime_start:, current_regime] = True

    # ADD REGIME COLUMN
    df["regime"] = "ranging"
    df.loc[df["trending_up"], "regime"] = "trending_up"
    df.loc[df["trending_down"], "regime"] = "trending_down"

    df = df.dropna().reset_index(drop=True)
    return df