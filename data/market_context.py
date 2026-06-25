"""7-dimension market context scorer (-100 to +100 per dimension)."""

from __future__ import annotations

from models import Bar, Indicators, MarketContext


def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def score_market_context(
    bars: list[Bar],
    indicators: Indicators,
) -> MarketContext:
    close = bars[-1].close if bars else 0.0

    # Trend: EMA alignment
    if indicators.ema_9 > indicators.ema_21 > indicators.ema_50:
        trend = 70.0
    elif indicators.ema_9 < indicators.ema_21 < indicators.ema_50:
        trend = -70.0
    else:
        spread = (indicators.ema_9 - indicators.ema_50) / max(indicators.ema_50, 1) * 1000
        trend = _clamp(spread)

    # Momentum: MACD histogram + RSI
    macd_score = _clamp(indicators.macd_histogram * 20)
    rsi_score = _clamp((indicators.rsi - 50) * 2)
    momentum = _clamp((macd_score + rsi_score) / 2)

    # Mean reversion: distance from BB + VWAP deviation
    bb_range = indicators.bb_upper - indicators.bb_lower
    if bb_range > 0:
        bb_pos = (close - indicators.bb_middle) / (bb_range / 2)
        bb_reversion = _clamp(-bb_pos * 60)
    else:
        bb_reversion = 0.0
    vwap_reversion = _clamp(-indicators.vwap_deviation * 5)
    mean_reversion = _clamp((bb_reversion + vwap_reversion) / 2)

    # Volatility: ATR relative to price
    atr_pct = indicators.atr / max(close, 1) * 100
    volatility = _clamp((atr_pct - 0.15) * 200)

    # Volume: recent vs average
    if len(bars) >= 10:
        recent_vol = sum(b.volume for b in bars[-5:]) / 5
        avg_vol = sum(b.volume for b in bars[-20:]) / min(20, len(bars))
        vol_ratio = recent_vol / max(avg_vol, 1)
        volume = _clamp((vol_ratio - 1) * 80)
    else:
        volume = 0.0

    # S/R proximity: distance to volume profile POC
    poc_dist = abs(close - indicators.volume_profile_poc)
    sr_proximity = _clamp(50 - poc_dist * 2)

    # Regime: composite trend + volatility
    if trend > 30 and momentum > 20:
        regime = 60.0
    elif trend < -30 and momentum < -20:
        regime = -60.0
    elif abs(mean_reversion) > 40:
        regime = mean_reversion * 0.5
    else:
        regime = trend * 0.3

    return MarketContext(
        trend=trend,
        momentum=momentum,
        mean_reversion=mean_reversion,
        volatility=volatility,
        volume=volume,
        sr_proximity=sr_proximity,
        regime=regime,
    )
