"""Shared domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


class SessionType(str, Enum):
    RTH = "RTH"
    OVERNIGHT = "OVERNIGHT"


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Indicators:
    ema_9: float
    ema_21: float
    ema_50: float
    macd: float
    macd_signal: float
    macd_histogram: float
    rsi: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    vwap: float
    vwap_deviation: float
    atr: float
    volume_profile_poc: float


@dataclass
class MarketContext:
    trend: float  # -100 to +100
    momentum: float
    mean_reversion: float
    volatility: float
    volume: float
    sr_proximity: float
    regime: float
    composite: float = 0.0

    def __post_init__(self) -> None:
        dims = [
            self.trend,
            self.momentum,
            self.mean_reversion,
            self.volatility,
            self.volume,
            self.sr_proximity,
            self.regime,
        ]
        self.composite = sum(dims) / len(dims)


@dataclass
class MarketSnapshot:
    timestamp: datetime
    last_price: float
    bars_5m: list[Bar]
    bars_1m: list[Bar]
    bars_1h: list[Bar]
    bars_daily: list[Bar]
    indicators: Indicators
    context: MarketContext
    dom_score: float = 0.0
    gex_bn: float = 0.0


@dataclass
class LLMDecision:
    action: Direction
    confidence: int
    stop_loss_points: float
    take_profit_points: float
    reasoning: str
    is_exit: bool = False


@dataclass
class Position:
    direction: Direction
    entry_price: float
    size: int
    entry_time: datetime
    stop_loss: float
    take_profit: float
    unrealized_pnl: float = 0.0
    initial_stop: float = 0.0
    max_favorable_price: float = 0.0
    max_adverse_price: float = 0.0
    breakeven_moved: bool = False
    trailing_active: bool = False
    bars_held: int = 0

    def __post_init__(self) -> None:
        if self.initial_stop == 0.0:
            self.initial_stop = self.stop_loss
        if self.max_favorable_price == 0.0:
            self.max_favorable_price = self.entry_price
        if self.max_adverse_price == 0.0:
            self.max_adverse_price = self.entry_price

    @property
    def is_long(self) -> bool:
        return self.direction == Direction.LONG

    @property
    def is_short(self) -> bool:
        return self.direction == Direction.SHORT

    @property
    def risk_points(self) -> float:
        """Initial risk in points (entry to original stop)."""
        return abs(self.entry_price - self.initial_stop)


@dataclass
class TradeRecord:
    direction: Direction
    entry_price: float
    exit_price: float
    size: int
    pnl: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str
    risk_points: float = 0.0
    mfe_points: float = 0.0
    mae_points: float = 0.0
    r_multiple: float = 0.0
    bars_held: int = 0


@dataclass
class AccountState:
    balance: float
    daily_pnl: float
    trades_today: int
    max_daily_loss: float = -1000.0
    max_daily_profit: float = 1500.0


@dataclass
class GateResult:
    passed: bool
    reason: str = ""
    adjusted_tp: float | None = None


@dataclass
class EngineState:
    position: Position | None = None
    cooldown_until: datetime | None = None
    trades_today: list[TradeRecord] = field(default_factory=list)
    hold_log: list[str] = field(default_factory=list)
    opposing_signal_count: int = 0
    last_opposing_signal_time: datetime | None = None
    blocked: bool = False
    block_reason: str = ""


@dataclass
class BracketOrder:
    direction: Direction
    size: int
    entry_price: float
    stop_loss: float
    take_profit: float
    order_id: str = ""


@dataclass
class PromptContext:
    snapshot: MarketSnapshot
    account: AccountState
    trades_today: list[TradeRecord]
    hold_log: list[str]
    position: Position | None = None
    exit_history: list[str] = field(default_factory=list)

    def to_user_prompt(self) -> str:
        pos_text = "FLAT"
        if self.position:
            p = self.position
            pos_text = (
                f"{p.direction.value} x{p.size} @ {p.entry_price:.2f} "
                f"SL={p.stop_loss:.2f} TP={p.take_profit:.2f} "
                f"P&L=${p.unrealized_pnl:.2f}"
            )

        trades_text = "\n".join(
            f"  {t.direction.value} {t.entry_price:.2f}->{t.exit_price:.2f} "
            f"P&L=${t.pnl:.2f} ({t.exit_reason})"
            for t in self.trades_today[-5:]
        ) or "  (none)"

        ctx = self.snapshot.context
        ind = self.snapshot.indicators

        return f"""## Market Dashboard
Price: {self.snapshot.last_price:.2f}
Time: {self.snapshot.timestamp.isoformat()}

## Market Context (7 dimensions, -100 to +100)
Trend: {ctx.trend:.1f} | Momentum: {ctx.momentum:.1f} | Mean Reversion: {ctx.mean_reversion:.1f}
Volatility: {ctx.volatility:.1f} | Volume: {ctx.volume:.1f} | S/R Proximity: {ctx.sr_proximity:.1f}
Regime: {ctx.regime:.1f} | Composite: {ctx.composite:.1f}

## Indicators
EMA 9/21/50: {ind.ema_9:.2f} / {ind.ema_21:.2f} / {ind.ema_50:.2f}
MACD: {ind.macd:.2f} (signal {ind.macd_signal:.2f}, hist {ind.macd_histogram:.2f})
RSI: {ind.rsi:.1f} | ATR: {ind.atr:.2f}
BB: {ind.bb_lower:.2f} / {ind.bb_middle:.2f} / {ind.bb_upper:.2f}
VWAP: {ind.vwap:.2f} (dev {ind.vwap_deviation:.2f})

## DOM Score: {self.snapshot.dom_score:.1f}
## GEX: ${self.snapshot.gex_bn:.2f}Bn

## Position
{pos_text}

## Account
Balance: ${self.account.balance:.2f} | Daily P&L: ${self.account.daily_pnl:.2f}
Trades today: {self.account.trades_today}

## Today's Trades
{trades_text}

## Recent Hold Log
{chr(10).join(f'  {h}' for h in self.hold_log[-5:]) or '  (none)'}
"""
