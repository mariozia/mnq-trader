"""Live/delayed Nasdaq futures data via Yahoo Finance (NQ=F).

Yahoo provides ~15-minute delayed CME E-mini Nasdaq-100 futures (NQ=F).
MNQ tracks the same index price — contract size differs, not the quote level.

This is good enough for paper trading and validating Claude on real market
structure. For real-time data + execution, wire your broker's feed instead.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from data.feeds.base import MarketDataFeed
from models import Bar

logger = logging.getLogger(__name__)


def _df_to_bars(df: pd.DataFrame) -> list[Bar]:
    if df is None or df.empty:
        return []
    bars: list[Bar] = []
    for ts, row in df.iterrows():
        if hasattr(ts, "to_pydatetime"):
            timestamp = ts.to_pydatetime()
            if timestamp.tzinfo:
                timestamp = timestamp.replace(tzinfo=None)
        else:
            timestamp = ts
        bars.append(
            Bar(
                timestamp=timestamp,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0) or 0),
            )
        )
    return bars


class YahooFuturesFeed(MarketDataFeed):
    """Fetches NQ/MNQ-equivalent futures bars from Yahoo Finance."""

    def __init__(self, symbol: str = "NQ=F") -> None:
        self.symbol = symbol
        self._ticker = None

    @property
    def source_name(self) -> str:
        return f"yahoo:{self.symbol}"

    def _get_ticker(self):
        if self._ticker is None:
            import yfinance as yf

            self._ticker = yf.Ticker(self.symbol)
        return self._ticker

    def _history(self, period: str, interval: str) -> pd.DataFrame:
        try:
            df = self._get_ticker().history(period=period, interval=interval)
            if df is None or df.empty:
                logger.warning("Yahoo returned no data for %s %s/%s", self.symbol, period, interval)
                return pd.DataFrame()
            return df
        except Exception as exc:
            logger.error("Yahoo fetch failed (%s %s): %s", period, interval, exc)
            return pd.DataFrame()

    def fetch_bar_sets(self, now: datetime | None = None) -> dict[str, list[Bar]]:
        # Yahoo limits: 1m→7d, 5m→60d, 1h→730d, 1d→max
        sets = {
            "5m": _df_to_bars(self._history("5d", "5m").tail(60)),
            "1m": _df_to_bars(self._history("1d", "1m").tail(60)),
            "1h": _df_to_bars(self._history("30d", "1h").tail(12)),
            "daily": _df_to_bars(self._history("60d", "1d").tail(14)),
        }
        if not sets["5m"]:
            raise RuntimeError(
                f"No bar data from Yahoo for {self.symbol}. "
                "Market may be closed or the symbol is unavailable."
            )
        return sets

    def last_price(self, bar_sets: dict[str, list[Bar]]) -> float:
        bars = bar_sets.get("5m", [])
        if not bars:
            return 0.0
        return bars[-1].close
