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
    def close_at_price(self, price: float, reason: str = "manual") -> TradeRecord | None:
        ...

    @abstractmethod
    def sync_state(self) -> ExchangeState:
        ...

    def check_bar_fills(self, high: float, low: float) -> TradeRecord | None:
        """Default: collapse the bar to its midpoint. MockBroker overrides this."""
        return self.check_bracket_fills((high + low) / 2)


class MockBroker(Broker):
    """Simulated exchange with realistic intrabar bracket fills."""

    def __init__(self, point_value: float = 2.0) -> None:
        self.point_value = point_value
        self._position: Position | None = None
        self._last_trade: TradeRecord | None = None
        self.clock: datetime | None = None  # simulated time for backtests

    def _now(self) -> datetime:
        return self.clock or datetime.now()

    def get_position(self) -> Position | None:
        return self._position

    def place_bracket(self, order: BracketOrder) -> str:
        order_id = order.order_id or str(uuid.uuid4())[:8]
        self._position = Position(
            direction=order.direction,
            entry_price=order.entry_price,
            size=order.size,
            entry_time=self._now(),
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            initial_stop=order.stop_loss,
        )
        return order_id

    def close_position(self, reason: str = "manual") -> TradeRecord | None:
        if not self._position:
            return None
        return self.close_at_price(self._position.entry_price, reason)

    def close_at_price(self, price: float, reason: str = "manual") -> TradeRecord | None:
        if not self._position:
            return None
        trade = self._build_trade(self._position, price, reason)
        self._position = None
        self._last_trade = trade
        return trade

    def check_bracket_fills(self, current_price: float) -> TradeRecord | None:
        """Single-price fill check (used by recon / live ticks)."""
        return self.check_bar_fills(current_price, current_price)

    def check_bar_fills(self, high: float, low: float) -> TradeRecord | None:
        """Intrabar fill check using the bar's range.

        Conservative ordering: if both the stop and target are touched in the
        same bar, assume the stop filled first.
        """
        if not self._position:
            return None

        pos = self._position
        close = (high + low) / 2
        pos.unrealized_pnl = self._calc_pnl(pos, close)
        pos.bars_held += 1

        if pos.is_long:
            if low <= pos.stop_loss:
                reason = "Trail stop" if pos.trailing_active or pos.breakeven_moved else "SL fill"
                return self.close_at_price(pos.stop_loss, reason)
            if high >= pos.take_profit:
                return self.close_at_price(pos.take_profit, "TP fill")
        else:
            if high >= pos.stop_loss:
                reason = "Trail stop" if pos.trailing_active or pos.breakeven_moved else "SL fill"
                return self.close_at_price(pos.stop_loss, reason)
            if low <= pos.take_profit:
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

    def _build_trade(self, pos: Position, exit_price: float, reason: str) -> TradeRecord:
        pnl = self._calc_pnl(pos, exit_price)
        if pos.is_long:
            mfe = pos.max_favorable_price - pos.entry_price
            mae = pos.entry_price - pos.max_adverse_price
        else:
            mfe = pos.entry_price - pos.max_favorable_price
            mae = pos.max_adverse_price - pos.entry_price
        risk = pos.risk_points
        pnl_points = pnl / (pos.size * self.point_value) if pos.size else 0.0
        r_multiple = pnl_points / risk if risk > 0 else 0.0
        return TradeRecord(
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            size=pos.size,
            pnl=pnl,
            entry_time=pos.entry_time,
            exit_time=self._now(),
            exit_reason=reason,
            risk_points=risk,
            mfe_points=mfe,
            mae_points=mae,
            r_multiple=r_multiple,
            bars_held=pos.bars_held,
        )


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

    def close_at_price(self, price: float, reason: str = "manual") -> TradeRecord | None:
        raise NotImplementedError("TopstepX live broker not yet implemented")

    def sync_state(self) -> ExchangeState:
        raise NotImplementedError("TopstepX live broker not yet implemented")
