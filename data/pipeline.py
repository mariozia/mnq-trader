"""Full market data pipeline: feed -> indicators -> context -> snapshot."""

from __future__ import annotations

import logging
from datetime import datetime

from config import AppConfig, DataFeed, TradingMode
from data.feeds.mock import MockDataFeed
from data.feeds.yahoo import YahooFuturesFeed
from data.gex_rh import GEXProvider, MockGEXProvider
from data.indicators import compute_indicators
from data.market_context import score_market_context
from dom.dom_analyzer import DOMAnalyzer
from models import MarketSnapshot

logger = logging.getLogger(__name__)


def create_feed(config: AppConfig) -> MockDataFeed | YahooFuturesFeed:
    if config.demo:
        return MockDataFeed(demo=True)
    if config.trading_mode == TradingMode.PAPER or config.data_feed == DataFeed.YAHOO:
        return YahooFuturesFeed(symbol=config.yahoo_symbol)
    return MockDataFeed()


class DataPipeline:
    """Fetches and processes market data every cycle."""

    def __init__(
        self,
        config: AppConfig | None = None,
        dom_analyzer: DOMAnalyzer | None = None,
        gex_provider: GEXProvider | None = None,
        demo: bool = False,
    ) -> None:
        if config is None:
            from config import AppConfig as AC

            config = AC(demo=demo)
        self.feed = create_feed(config)
        self.dom_analyzer = dom_analyzer or DOMAnalyzer()
        self.gex_provider = gex_provider or MockGEXProvider()
        self._last_fetch: datetime | None = None

    @property
    def source(self) -> str:
        return self.feed.source_name

    def fetch_snapshot(self, now: datetime | None = None) -> MarketSnapshot:
        now = now or datetime.now()
        bar_sets = self.feed.fetch_bar_sets(now)
        self._last_fetch = now

        primary = bar_sets["5m"]
        indicators = compute_indicators(primary)
        context = score_market_context(primary, indicators)
        last_price = self.feed.last_price(bar_sets)

        # Update DOM mock with current mid for more realistic imbalance
        self.dom_analyzer.book.update(mid_price=last_price)
        dom_score = self.dom_analyzer.get_score()

        logger.debug(
            "Snapshot [%s] price=%.2f trend=%.0f bars_5m=%d",
            self.source,
            last_price,
            context.trend,
            len(primary),
        )

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
