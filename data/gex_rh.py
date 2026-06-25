"""Mock GEX data from Robinhood options (NDX+SPX). Live adapter stub included."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from datetime import datetime


class GEXProvider(ABC):
    @abstractmethod
    def get_gex_bn(self) -> float:
        """Return GEX in billions of dollars."""
        ...


class MockGEXProvider(GEXProvider):
    """Simulates GEX oscillating between -3Bn and +3Bn."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def get_gex_bn(self) -> float:
        return self._rng.uniform(-2.5, 2.5)


class RobinhoodGEXProvider(GEXProvider):
    """Stub for live Robinhood options GEX feed (NDX + SPX)."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self._authenticated = False

    def authenticate(self) -> None:
        raise NotImplementedError(
            "Robinhood GEX integration requires credentials. "
            "Implement NDX+SPX options chain GEX calculation here."
        )

    def get_gex_bn(self) -> float:
        if not self._authenticated:
            self.authenticate()
        raise NotImplementedError("Live GEX not yet implemented")


def create_gex_provider(mode: str = "mock", **kwargs) -> GEXProvider:
    if mode == "live":
        return RobinhoodGEXProvider(
            username=kwargs.get("username", ""),
            password=kwargs.get("password", ""),
        )
    return MockGEXProvider()
