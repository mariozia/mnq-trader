"""Blind recon: sync engine state with exchange every 5 seconds."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from execution.broker import Broker, ExchangeState
from models import Position
from state.store import StateStore

logger = logging.getLogger(__name__)


@dataclass
class ReconResult:
    synced: bool
    action: str = ""
    alert: bool = False


class BlindRecon:
    """Catches bracket fills the engine missed and detects unknown positions."""

    def __init__(
        self,
        broker: Broker,
        state_store: StateStore,
        discord_webhook: str = "",
    ) -> None:
        self.broker = broker
        self.state = state_store
        self.discord_webhook = discord_webhook

    def run(self, current_price: float) -> ReconResult:
        exchange = self.broker.sync_state()
        engine_pos = self.state.state.position
        exchange_pos = exchange.position

        # Check bracket fills first
        fill = self.broker.check_bracket_fills(current_price)
        if fill:
            self.state.state.position = None
            self.state.record_trade(fill)
            self.state.start_cooldown()
            logger.info("Recon: bracket fill detected — %s P&L=$%.2f", fill.exit_reason, fill.pnl)
            return ReconResult(synced=True, action=f"bracket_fill:{fill.exit_reason}")

        if engine_pos and not exchange_pos:
            self.state.state.position = None
            logger.info("Recon: engine had position, exchange flat — synced")
            return ReconResult(synced=True, action="position_cleared")

        if not engine_pos and exchange_pos:
            self.state.state.blocked = True
            self.state.state.block_reason = "Unknown position on exchange!"
            self._alert("UNKNOWN POSITION on exchange — blocking all orders")
            return ReconResult(
                synced=False,
                action="unknown_position",
                alert=True,
            )

        if engine_pos and exchange_pos:
            if engine_pos.size != exchange_pos.size:
                self.state.state.position = exchange_pos
                logger.warning(
                    "Recon: size mismatch engine=%d exchange=%d — synced to exchange",
                    engine_pos.size,
                    exchange_pos.size,
                )
                return ReconResult(synced=True, action="size_synced")

        return ReconResult(synced=True)

    def _alert(self, message: str) -> None:
        logger.critical("ALERT: %s", message)
        if self.discord_webhook:
            try:
                import urllib.request

                import json

                payload = json.dumps({"content": f"🚨 MNQ Trader: {message}"}).encode()
                req = urllib.request.Request(
                    self.discord_webhook,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                logger.error("Discord alert failed: %s", e)
