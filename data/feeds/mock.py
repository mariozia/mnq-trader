"""Simulated bar feed (wraps BarBuilder)."""

from __future__ import annotations

from datetime import datetime

from data.bar_builder import BarBuilder
from data.feeds.base import MarketDataFeed
from models import Bar


class MockDataFeed(MarketDataFeed):
    def __init__(self, bar_builder: BarBuilder | None = None, demo: bool = False) -> None:
        if demo and bar_builder is None:
            bar_builder = BarBuilder(seed=42, trend_bias=-1.0)
        self.bar_builder = bar_builder or BarBuilder()

    @property
    def source_name(self) -> str:
        return "mock"

    def fetch_bar_sets(self, now: datetime | None = None) -> dict[str, list[Bar]]:
        return self.bar_builder.generate_mock_bars(now=now or datetime.now())

    def last_price(self, bar_sets: dict[str, list[Bar]]) -> float:
        bars = bar_sets.get("5m", [])
        return BarBuilder.last_price(bars)
