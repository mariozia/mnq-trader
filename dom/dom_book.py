"""Real-time order book via WebSocket (mock implementation)."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class OrderBookLevel:
    price: float
    size: int


class DOMBook:
    """Depth of Market book. Mock generates realistic bid/ask imbalance."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._mid = 21_500.0
        self.bids: list[OrderBookLevel] = []
        self.asks: list[OrderBookLevel] = []
        self._refresh()

    def _refresh(self) -> None:
        self.bids = []
        self.asks = []
        for i in range(10):
            bid_size = int(abs(self._rng.gauss(50, 20)))
            ask_size = int(abs(self._rng.gauss(50, 20)))
            self.bids.append(
                OrderBookLevel(price=self._mid - 0.25 * (i + 1), size=bid_size)
            )
            self.asks.append(
                OrderBookLevel(price=self._mid + 0.25 * (i + 1), size=ask_size)
            )

    def update(self, mid_price: float | None = None) -> None:
        if mid_price:
            self._mid = mid_price
        self._refresh()

    @property
    def total_bid_size(self) -> int:
        return sum(l.size for l in self.bids)

    @property
    def total_ask_size(self) -> int:
        return sum(l.size for l in self.asks)

    @property
    def imbalance(self) -> float:
        """Positive = buyers dominate, negative = sellers dominate."""
        total = self.total_bid_size + self.total_ask_size
        if total == 0:
            return 0.0
        return (self.total_bid_size - self.total_ask_size) / total * 100
