"""Dual prompt engine: parallel entry, sequential exit with reversal logic."""

from __future__ import annotations

import logging
from datetime import datetime

from config import AIMode, AppConfig, SIZING
from engine.directional_engine import DirectionalEngine
from execution.brackets import build_bracket
from models import Direction, LLMDecision, Position, PromptContext, TradeRecord

logger = logging.getLogger(__name__)


class DualEngine(DirectionalEngine):
    """Both short-only and long-only prompts with consensus entry and reversal exits."""

    def __init__(self, config: AppConfig) -> None:
        config = AppConfig(
            trading_mode=config.trading_mode,
            ai_mode=AIMode.DUAL,
            demo=config.demo,
            gates=config.gates,
            engine=config.engine,
            anthropic_api_key=config.anthropic_api_key,
            anthropic_model=config.anthropic_model,
            topstepx_api_key=config.topstepx_api_key,
            topstepx_username=config.topstepx_username,
            discord_webhook_url=config.discord_webhook_url,
        )
        super().__init__(config)
        self.mode = AIMode.DUAL
        sizing = SIZING[AIMode.DUAL]
        self.rth_size = sizing.rth
        self.overnight_size = sizing.overnight

    def _resolve_direction(self) -> Direction:
        return Direction.HOLD  # dual mode has no single allowed direction

    def _handle_flat(
        self, ctx: PromptContext, snapshot, now: datetime
    ) -> dict:
        short_decision = self.trader.call_short(ctx)
        long_decision = self.trader.call_long(ctx)

        entry = self._consensus_entry(short_decision, long_decision)
        if entry is None:
            self.state_store.log_hold(
                f"No setup: SHORT={short_decision.action.value}({short_decision.confidence}) "
                f"LONG={long_decision.action.value}({long_decision.confidence})"
            )
            return {"action": "hold", "reason": "No consensus setup"}

        direction, decision = entry

        gate = self.gates.evaluate_entry(decision, snapshot)
        if not gate.passed:
            self.state_store.log_hold(f"Gate blocked: {gate.reason}")
            return {"action": "gate_blocked", "reason": gate.reason}

        size = self.scheduler.contract_size(
            self.rth_size, self.overnight_size, now
        )
        bracket = build_bracket(
            decision, direction, size, snapshot.last_price, adjusted_tp=gate.adjusted_tp
        )

        order_id = self.broker.place_bracket(bracket)
        self.state_store.state.position = self.broker.get_position()
        self.state_store.reset_opposing_signals()
        self.state_store.log_hold(
            f"ENTER {direction.value} x{size} @ {snapshot.last_price:.2f} "
            f"conf={decision.confidence}"
        )

        return {
            "action": "enter",
            "direction": direction.value,
            "size": size,
            "order_id": order_id,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
        }

    def _handle_in_position(
        self, ctx: PromptContext, snapshot, position: Position
    ) -> dict:
        fill = self.broker.check_bracket_fills(snapshot.last_price)
        if fill:
            return self._process_exit(fill)

        # Stage 1: same-direction exit evaluation
        if position.is_long:
            same_decision = self.trader.call_long(ctx, exit_mode=True)
        else:
            same_decision = self.trader.call_short(ctx, exit_mode=True)

        if same_decision.action == Direction.CLOSE:
            trade = self.broker.close_at_price(
                snapshot.last_price, reason="LLM exit (thesis broken)"
            )
            if trade:
                return self._process_exit(trade)

        # Stage 2: opposing direction check for reversal
        if position.is_long:
            opposing = self.trader.call_short(ctx)
            opposing_dir = Direction.SHORT
        else:
            opposing = self.trader.call_long(ctx)
            opposing_dir = Direction.LONG

        if opposing.action != opposing_dir:
            self.state_store.reset_opposing_signals()
            self.state_store.log_hold(f"Holding: opposing says {opposing.action.value}")
            return {"action": "hold_position", "reason": "No reversal signal"}

        count = self.state_store.increment_opposing_signal(snapshot.timestamp)
        required = self.config.engine.reversal_consecutive_signals

        if count < required:
            self.state_store.log_hold(
                f"Anti-flip: signal {count}/{required} building..."
            )
            return {"action": "hold_position", "reason": f"Anti-flip {count}/{required}"}

        gate = self.gates.evaluate_reversal(opposing, snapshot, count)
        if not gate.passed:
            self.state_store.log_hold(f"Reversal gate blocked: {gate.reason}")
            return {"action": "gate_blocked", "reason": gate.reason}

        # Reversal: close current, skip cooldown, enter opposing
        close_trade = self.broker.close_at_price(
            snapshot.last_price, reason="Reversal close"
        )
        if close_trade:
            self.risk.record_trade(close_trade.pnl)
            self.state_store.record_trade(close_trade)

        self.state_store.clear_cooldown()
        self.state_store.reset_opposing_signals()

        size = self.scheduler.contract_size(
            self.rth_size, self.overnight_size, snapshot.timestamp
        )
        bracket = build_bracket(
            opposing, opposing_dir, size, snapshot.last_price, adjusted_tp=gate.adjusted_tp
        )
        order_id = self.broker.place_bracket(bracket)
        self.state_store.state.position = self.broker.get_position()

        logger.info("REVERSAL: %s -> %s", position.direction.value, opposing_dir.value)
        return {
            "action": "reversal",
            "from": position.direction.value,
            "to": opposing_dir.value,
            "size": size,
            "order_id": order_id,
            "confidence": opposing.confidence,
        }

    @staticmethod
    def _consensus_entry(
        short: LLMDecision, long: LLMDecision
    ) -> tuple[Direction, LLMDecision] | None:
        """Decision matrix from spec."""
        s = short.action
        l = long.action

        if s == Direction.SHORT and l == Direction.HOLD:
            return Direction.SHORT, short
        if s == Direction.HOLD and l == Direction.LONG:
            return Direction.LONG, long
        # SHORT + LONG = conflict, HOLD + HOLD = no setup
        return None
