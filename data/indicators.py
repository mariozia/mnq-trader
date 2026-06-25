"""Technical indicator calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models import Bar, Indicators


def bars_to_df(bars: list[Bar]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_indicators(bars: list[Bar]) -> Indicators:
    if len(bars) < 50:
        last = bars[-1].close if bars else 0.0
        return Indicators(
            ema_9=last,
            ema_21=last,
            ema_50=last,
            macd=0.0,
            macd_signal=0.0,
            macd_histogram=0.0,
            rsi=50.0,
            bb_upper=last,
            bb_middle=last,
            bb_lower=last,
            vwap=last,
            vwap_deviation=0.0,
            atr=10.0,
            volume_profile_poc=last,
        )

    df = bars_to_df(bars)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    ema9 = ema(close, 9).iloc[-1]
    ema21 = ema(close, 21).iloc[-1]
    ema50 = ema(close, 50).iloc[-1]

    macd_line = ema(close, 12) - ema(close, 26)
    macd_signal = ema(macd_line, 9)
    macd_val = macd_line.iloc[-1]
    signal_val = macd_signal.iloc[-1]
    hist = macd_val - signal_val

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (100 - (100 / (1 + rs))).iloc[-1]

    bb_mid = close.rolling(20).mean().iloc[-1]
    bb_std = close.rolling(20).std().iloc[-1]
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    typical = (high + low + close) / 3
    cum_vol = volume.cumsum()
    vwap = (typical * volume).cumsum() / cum_vol.replace(0, np.nan)
    vwap_val = vwap.iloc[-1]
    vwap_dev = close.iloc[-1] - vwap_val

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    # Volume profile POC: price level with highest volume (simplified)
    price_bins = np.linspace(close.min(), close.max(), 20)
    vol_at_price = np.zeros(len(price_bins) - 1)
    for _, row in df.iterrows():
        idx = np.digitize(row["close"], price_bins) - 1
        idx = max(0, min(idx, len(vol_at_price) - 1))
        vol_at_price[idx] += row["volume"]
    poc_idx = int(np.argmax(vol_at_price))
    poc = (price_bins[poc_idx] + price_bins[poc_idx + 1]) / 2

    return Indicators(
        ema_9=float(ema9),
        ema_21=float(ema21),
        ema_50=float(ema50),
        macd=float(macd_val),
        macd_signal=float(signal_val),
        macd_histogram=float(hist),
        rsi=float(rsi) if not np.isnan(rsi) else 50.0,
        bb_upper=float(bb_upper),
        bb_middle=float(bb_mid),
        bb_lower=float(bb_lower),
        vwap=float(vwap_val),
        vwap_deviation=float(vwap_dev),
        atr=float(atr) if not np.isnan(atr) else 10.0,
        volume_profile_poc=float(poc),
    )
