"""Central configuration for the MNQ trading engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class TradingMode(str, Enum):
    MOCK = "mock"
    LIVE = "live"


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
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-20250514"
    topstepx_api_key: str = ""
    topstepx_username: str = ""
    discord_webhook_url: str = ""

    @classmethod
    def from_env(cls, ai_mode: AIMode | None = None) -> AppConfig:
        mode_str = os.getenv("TRADING_MODE", "mock").lower()
        return cls(
            trading_mode=TradingMode(mode_str),
            ai_mode=ai_mode or AIMode.DUAL,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            topstepx_api_key=os.getenv("TOPSTEPX_API_KEY", ""),
            topstepx_username=os.getenv("TOPSTEPX_USERNAME", ""),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
        )
