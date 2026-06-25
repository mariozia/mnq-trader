"""Central configuration for the MNQ trading engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class TradingMode(str, Enum):
    MOCK = "mock"
    PAPER = "paper"  # real market data + simulated fills + real Claude
    LIVE = "live"    # real data + real broker + real Claude


class DataFeed(str, Enum):
    MOCK = "mock"
    YAHOO = "yahoo"


class AIMode(str, Enum):
    SHORT_ONLY = "short-only"
    LONG_ONLY = "long-only"
    DUAL = "dual"


@dataclass(frozen=True)
class SizingConfig:
    rth: int
    overnight: int


@dataclass(frozen=True)
class GateConfig:
    min_confidence_entry: int = 65
    min_confidence_reversal: int = 70
    dom_threshold: float = 30.0
    gex_pinned_threshold_bn: float = 2.0
    min_rr_ratio: float = 1.5
    gex_tp_amplify: float = 1.3
    gex_tp_dampen: float = 0.7


@dataclass(frozen=True)
class EngineConfig:
    cycle_seconds: int = 60
    recon_seconds: int = 5
    cooldown_minutes: int = 15
    max_trades_per_day: int = 4
    reversal_consecutive_signals: int = 2
    symbol: str = "MNQ"
    point_value: float = 2.0  # $2 per point per contract on MNQ


@dataclass
class ProfitConfig:
    """Dynamic exit management — the 'take the green while it's there' layer.

    All thresholds are expressed in R (multiples of initial risk = distance
    from entry to the original stop), so 'green enough' scales with each trade
    instead of being a fixed dollar amount.
    """

    # Breakeven: once price runs +breakeven_trigger_r in our favor, pull the
    # stop up to entry (+ a small offset) so a winner can't become a loser.
    breakeven_enabled: bool = True
    breakeven_trigger_r: float = 0.5
    breakeven_offset_points: float = 1.0

    # Trailing stop: once price runs +trailing_trigger_r, trail the stop
    # trailing_distance_r behind the best price seen.
    trailing_enabled: bool = True
    trailing_trigger_r: float = 1.0
    trailing_distance_r: float = 0.75

    # Scalp take: immediately market-close at +scalp_target_r. This mimics the
    # "instantly green, grab it" behavior. Off by default so you can A/B it.
    scalp_enabled: bool = False
    scalp_target_r: float = 0.75

    # Force a flat exit after N bars if the trade never got green (0 = off).
    max_hold_bars: int = 0


SIZING: dict[AIMode, SizingConfig] = {
    AIMode.SHORT_ONLY: SizingConfig(rth=10, overnight=5),
    AIMode.LONG_ONLY: SizingConfig(rth=10, overnight=5),
    AIMode.DUAL: SizingConfig(rth=5, overnight=3),
}


@dataclass
class AppConfig:
    trading_mode: TradingMode = TradingMode.MOCK
    ai_mode: AIMode = AIMode.DUAL
    demo: bool = False
    gates: GateConfig = field(default_factory=GateConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    profit: ProfitConfig = field(default_factory=ProfitConfig)
    persist_state: bool = True
    data_feed: DataFeed = DataFeed.MOCK
    yahoo_symbol: str = "NQ=F"
    paper_journal_path: str = ".paper/trades.csv"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-6"
    topstepx_api_key: str = ""
    topstepx_username: str = ""
    discord_webhook_url: str = ""

    @classmethod
    def from_env(cls, ai_mode: AIMode | None = None) -> AppConfig:
        mode_str = os.getenv("TRADING_MODE", "mock").lower()
        feed_str = os.getenv("DATA_FEED", "mock").lower()
        return cls(
            trading_mode=TradingMode(mode_str),
            ai_mode=ai_mode or AIMode.DUAL,
            data_feed=DataFeed(feed_str),
            yahoo_symbol=os.getenv("YAHOO_SYMBOL", "NQ=F"),
            paper_journal_path=os.getenv("PAPER_JOURNAL", ".paper/trades.csv"),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            topstepx_api_key=os.getenv("TOPSTEPX_API_KEY", ""),
            topstepx_username=os.getenv("TOPSTEPX_USERNAME", ""),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
        )
