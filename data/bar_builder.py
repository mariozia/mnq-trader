"""Build OHLCV bars from tick/stream data or synthetic mock feed."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from models import Bar


class BarBuilder:
    """Aggregates ticks into multi-timeframe bar sets with rolling state."""

    def __init__(self, seed: int | None = None, trend_bias: float = 0.0) -> None:
        self._rng = random.Random(seed)
        self._base_price = 21_500.0
        self._trend_bias = trend_bias
        self._series: dict[str, list[Bar]] = {}
        self._intervals: dict[str, timedelta] = {
            "5m": timedelta(minutes=5),
            "1m": timedelta(minutes=1),
            "1h": timedelta(hours=1),
            "daily": timedelta(days=1),
        }
        self._counts: dict[str, int] = {
            "5m": 60,
            "1m": 60,
            "1h": 12,
            "daily": 14,
        }

    def generate_mock_bars(
        self,
        count_5m: int = 60,
        count_1m: int = 60,
        count_1h: int = 12,
        count_daily: int = 14,
        now: datetime | None = None,
    ) -> dict[str, list[Bar]]:
        now = now or datetime.now()
        self._counts = {
            "5m": count_5m,
            "1m": count_1m,
            "1h": count_1h,
            "daily": count_daily,
        }

        result: dict[str, list[Bar]] = {}
        for key, interval in self._intervals.items():
            count = self._counts[key]
            if key not in self._series:
                self._series[key] = self._bootstrap(now, count, interval)
            else:
                self._series[key] = self._append_bar(self._series[key], now, interval, count)
            result[key] = list(self._series[key])
        return result

    def _bootstrap(self, end: datetime, count: int, interval: timedelta) -> list[Bar]:
        bars: list[Bar] = []
        price = self._base_price
        ts = end - interval * count
        for _ in range(count):
            bar, price = self._make_bar(ts, price)
            bars.append(bar)
            ts += interval
        self._base_price = price
        return bars

    def _append_bar(
        self, bars: list[Bar], now: datetime, interval: timedelta, max_count: int
    ) -> list[Bar]:
        last = bars[-1]
        if (now - last.timestamp) < interval:
            return bars
        new_ts = last.timestamp + interval
        bar, price = self._make_bar(new_ts, last.close)
        self._base_price = price
        updated = bars + [bar]
        return updated[-max_count:]

    def _make_bar(self, ts: datetime, price: float) -> tuple[Bar, float]:
        drift = self._rng.gauss(self._trend_bias, 2.5)
        o = price
        c = price + drift
        h = max(o, c) + abs(self._rng.gauss(0, 1.5))
        l = min(o, c) - abs(self._rng.gauss(0, 1.5))
        v = abs(self._rng.gauss(5000, 1500))
        return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=v), c

    @staticmethod
    def from_closes(
        timestamps: list[datetime],
        closes: list[float],
        interval: timedelta,
    ) -> list[Bar]:
        bars: list[Bar] = []
        for i, (ts, close) in enumerate(zip(timestamps, closes)):
            prev = closes[i - 1] if i > 0 else close
            high = max(prev, close) * 1.0005
            low = min(prev, close) * 0.9995
            bars.append(
                Bar(
                    timestamp=ts,
                    open=prev,
                    high=high,
                    low=low,
                    close=close,
                    volume=5000.0,
                )
            )
        return bars

    @staticmethod
    def last_price(bars: list[Bar]) -> float:
        return bars[-1].close if bars else 0.0
