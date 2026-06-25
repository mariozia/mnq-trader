"""Full market data pipeline: bars -> indicators -> context -> snapshot."""

from __future__ import annotations

from datetime import datetime

from data.bar_builder import BarBuilder
from data.gex_rh import GEXProvider, MockGEXProvider
from data.indicators import compute_indicators
from data.market_context import score_market_context
from dom.dom_analyzer import DOMAnalyzer
from models import MarketSnapshot


class DataPipeline:
    """Fetches and processes market data every cycle."""

    def __init__(
        self,
        bar_builder: BarBuilder | None = None,
        dom_analyzer: DOMAnalyzer | None = None,
        gex_provider: GEXProvider | None = None,
        demo: bool = False,
    ) -> None:
        if demo and bar_builder is None:
            bar_builder = BarBuilder(seed=42, trend_bias=-1.0)
        self.bar_builder = bar_builder or BarBuilder()
        self.dom_analyzer = dom_analyzer or DOMAnalyzer()
        self.gex_provider = gex_provider or MockGEXProvider()

    def fetch_snapshot(self, now: datetime | None = None) -> MarketSnapshot:
        now = now or datetime.now()
        bar_sets = self.bar_builder.generate_mock_bars(now=now)

        primary = bar_sets["5m"]
        indicators = compute_indicators(primary)
        context = score_market_context(primary, indicators)
        last_price = BarBuilder.last_price(primary)
        dom_score = self.dom_analyzer.get_score()

        return MarketSnapshot(
            timestamp=now,
            last_price=last_price,
            bars_5m=bar_sets["5m"],
            bars_1m=bar_sets["1m"],
            bars_1h=bar_sets["1h"],
            bars_daily=bar_sets["daily"],
            indicators=indicators,
            context=context,
            dom_score=dom_score,
            gex_bn=self.gex_provider.get_gex_bn(),
        )
