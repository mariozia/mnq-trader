"""Market data feed interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from models import Bar


class MarketDataFeed(ABC):
    @abstractmethod
    def fetch_bar_sets(self, now: datetime | None = None) -> dict[str, list[Bar]]:
        ...

    @abstractmethod
    def last_price(self, bar_sets: dict[str, list[Bar]]) -> float:
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        ...
