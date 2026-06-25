"""Broker abstraction with mock paper trading implementation."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from models import BracketOrder, Direction, Position, TradeRecord


@dataclass
class ExchangeState:
    position: Position | None = None
    pending_bracket: BracketOrder | None = None


class Broker(ABC):
    @abstractmethod
    def get_position(self) -> Position | None:
        ...

    @abstractmethod
    def place_bracket(self, order: BracketOrder) -> str:
        ...

    @abstractmethod
    def close_position(self, reason: str = "manual") -> TradeRecord | None:
        ...

    @abstractmethod
    def check_bracket_fills(self, current_price: float) -> TradeRecord | None:
        ...

    @abstractmethod
    def sync_state(self) -> ExchangeState:
        ...


class MockBroker(Broker):
    """Simulated exchange with bracket SL/TP fills."""

    def __init__(self, point_value: float = 2.0) -> None:
        self.point_value = point_value
        self._position: Position | None = None
        self._last_trade: TradeRecord | None = None

    def get_position(self) -> Position | None:
        return self._position

    def place_bracket(self, order: BracketOrder) -> str:
        order_id = order.order_id or str(uuid.uuid4())[:8]
        self._position = Position(
            direction=order.direction,
            entry_price=order.entry_price,
            size=order.size,
            entry_time=datetime.now(),
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
        )
        return order_id

    def close_position(self, reason: str = "manual") -> TradeRecord | None:
        if not self._position:
            return None

        pos = self._position
        exit_price = pos.entry_price  # market close at current (simplified)
        pnl = self._calc_pnl(pos, exit_price)

        trade = TradeRecord(
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            size=pos.size,
            pnl=pnl,
            entry_time=pos.entry_time,
            exit_time=datetime.now(),
            exit_reason=reason,
        )
        self._position = None
        self._last_trade = trade
        return trade

    def close_at_price(self, price: float, reason: str = "manual") -> TradeRecord | None:
        if not self._position:
            return None
        pos = self._position
        pnl = self._calc_pnl(pos, price)
        trade = TradeRecord(
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=price,
            size=pos.size,
            pnl=pnl,
            entry_time=pos.entry_time,
            exit_time=datetime.now(),
            exit_reason=reason,
        )
        self._position = None
        self._last_trade = trade
        return trade

    def check_bracket_fills(self, current_price: float) -> TradeRecord | None:
        if not self._position:
            return None

        pos = self._position
        pos.unrealized_pnl = self._calc_pnl(pos, current_price)

        if pos.is_long:
            if current_price <= pos.stop_loss:
                return self.close_at_price(pos.stop_loss, "SL fill")
            if current_price >= pos.take_profit:
                return self.close_at_price(pos.take_profit, "TP fill")
        elif pos.is_short:
            if current_price >= pos.stop_loss:
                return self.close_at_price(pos.stop_loss, "SL fill")
            if current_price <= pos.take_profit:
                return self.close_at_price(pos.take_profit, "TP fill")

        return None

    def sync_state(self) -> ExchangeState:
        return ExchangeState(position=self._position)

    def _calc_pnl(self, pos: Position, exit_price: float) -> float:
        points = (
            (exit_price - pos.entry_price)
            if pos.is_long
            else (pos.entry_price - exit_price)
        )
        return points * pos.size * self.point_value


class TopstepXBroker(Broker):
    """Stub for live TopstepX integration."""

    def __init__(self, api_key: str, username: str) -> None:
        self.api_key = api_key
        self.username = username

    def get_position(self) -> Position | None:
        raise NotImplementedError("TopstepX live broker not yet implemented")

    def place_bracket(self, order: BracketOrder) -> str:
        raise NotImplementedError("TopstepX live broker not yet implemented")

    def close_position(self, reason: str = "manual") -> TradeRecord | None:
        raise NotImplementedError("TopstepX live broker not yet implemented")

    def check_bracket_fills(self, current_price: float) -> TradeRecord | None:
        raise NotImplementedError("TopstepX live broker not yet implemented")

    def sync_state(self) -> ExchangeState:
        raise NotImplementedError("TopstepX live broker not yet implemented")
