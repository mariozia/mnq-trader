"""Short-only / long-only directional engine (base class)."""

from __future__ import annotations

import logging
from datetime import datetime

from ai.trader import Trader
from config import AIMode, AppConfig, SIZING
from data.pipeline import DataPipeline
from dom.dom_analyzer import DOMAnalyzer
from execution.brackets import build_bracket
from execution.broker import Broker, MockBroker
from execution.profit_manager import ProfitManager
from gates.chain import GateChain
from models import (
    AccountState,
    Direction,
    LLMDecision,
    Position,
    PromptContext,
    TradeRecord,
)
from risk.manager import RiskManager
from state.store import StateStore

from engine.recon import BlindRecon
from engine.scheduler import Scheduler

logger = logging.getLogger(__name__)


class DirectionalEngine:
    """Base engine for short-only and long-only modes."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.mode = config.ai_mode
        self.allowed_direction = self._resolve_direction()

        self.pipeline = DataPipeline(dom_analyzer=DOMAnalyzer(), demo=config.demo)
        self.trader = Trader(config)
        self.scheduler = Scheduler()
        self.state_store = StateStore(persist=config.persist_state)
        self.profit_manager = ProfitManager(config.profit)

        sizing = SIZING[self.mode]
        self.rth_size = sizing.rth
        self.overnight_size = sizing.overnight

        self.account = AccountState(
            balance=50_000.0,
            daily_pnl=0.0,
            trades_today=0,
        )
        self.risk = RiskManager(
            self.account, max_trades_per_day=config.engine.max_trades_per_day
        )
        self.gates = GateChain(config.gates, self.pipeline.dom_analyzer, self.risk)
        self.broker: Broker = self._create_broker()
        self.recon = BlindRecon(
            self.broker, self.state_store, config.discord_webhook_url
        )

        self._cycle_count = 0

    def _resolve_direction(self) -> Direction:
        if self.mode == AIMode.SHORT_ONLY:
            return Direction.SHORT
        if self.mode == AIMode.LONG_ONLY:
            return Direction.LONG
        raise ValueError("DirectionalEngine requires short-only or long-only mode")

    def _create_broker(self) -> Broker:
        from config import TradingMode
        from execution.broker import TopstepXBroker

        if self.config.trading_mode == TradingMode.LIVE and self.config.topstepx_api_key:
            return TopstepXBroker(
                api_key=self.config.topstepx_api_key,
                username=self.config.topstepx_username,
            )
        return MockBroker(point_value=self.config.engine.point_value)

    def run_cycle(self, now: datetime | None = None) -> dict:
        """Single decision cycle."""
        now = now or datetime.now()
        self._cycle_count += 1
        if hasattr(self.broker, "clock"):
            self.broker.clock = now
        snapshot = self.pipeline.fetch_snapshot(now)

        if self.scheduler.should_hard_close(now):
            return self._hard_close("RTH hard close", now)

        if not self.scheduler.is_trading_window(now):
            return {"action": "skip", "reason": "Outside trading window"}

        if self.state_store.state.blocked:
            return {"action": "blocked", "reason": self.state_store.state.block_reason}

        recon = self.recon.run(snapshot.last_price)
        if recon.alert:
            return {"action": "alert", "reason": recon.action}

        if self.state_store.is_in_cooldown(now):
            return {"action": "cooldown", "reason": "In cooldown period"}

        position = self.broker.get_position()
        self.state_store.state.position = position

        prompt_ctx = PromptContext(
            snapshot=snapshot,
            account=self.account,
            trades_today=self.state_store.state.trades_today,
            hold_log=self.state_store.state.hold_log,
            position=position,
        )

        if position:
            return self._handle_in_position(prompt_ctx, snapshot, position, now)
        return self._handle_flat(prompt_ctx, snapshot, now)

    def reset_for_new_day(self) -> None:
        """Reset daily risk counters and cooldown (used between backtest days)."""
        self.risk.reset_daily()
        self.state_store.clear_cooldown()
        self.state_store.reset_opposing_signals()

    @staticmethod
    def _bar_hl(snapshot) -> tuple[float, float]:
        if snapshot.bars_5m:
            bar = snapshot.bars_5m[-1]
            return bar.high, bar.low
        return snapshot.last_price, snapshot.last_price

    def _handle_flat(
        self, ctx: PromptContext, snapshot, now: datetime
    ) -> dict:
        decision = self._call_llm(ctx, exit_mode=False)

        if decision.action == Direction.HOLD:
            self.state_store.log_hold(f"Flat: {decision.reasoning}")
            return {"action": "hold", "reason": decision.reasoning}

        if decision.action != self.allowed_direction:
            self.state_store.log_hold(
                f"Direction blocked: LLM said {decision.action.value}"
            )
            return {"action": "blocked", "reason": f"Wrong direction: {decision.action.value}"}

        gate = self.gates.evaluate_entry(
            decision, snapshot, allowed_direction=self.allowed_direction
        )
        if not gate.passed:
            self.state_store.log_hold(f"Gate blocked: {gate.reason}")
            return {"action": "gate_blocked", "reason": gate.reason}

        size = self.scheduler.contract_size(
            self.rth_size, self.overnight_size, now
        )
        bracket = build_bracket(
            decision,
            self.allowed_direction,
            size,
            snapshot.last_price,
            adjusted_tp=gate.adjusted_tp,
        )

        order_id = self.broker.place_bracket(bracket)
        self.state_store.state.position = self.broker.get_position()
        self.state_store.log_hold(
            f"ENTER {self.allowed_direction.value} x{size} @ {snapshot.last_price:.2f} "
            f"SL={bracket.stop_loss:.2f} TP={bracket.take_profit:.2f} conf={decision.confidence}"
        )

        return {
            "action": "enter",
            "direction": self.allowed_direction.value,
            "size": size,
            "order_id": order_id,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
        }

    def _handle_in_position(
        self, ctx: PromptContext, snapshot, position: Position, now: datetime
    ) -> dict:
        high, low = self._bar_hl(snapshot)

        # 1. Tighten breakeven / trailing stop against this bar.
        self.profit_manager.update_trailing(position, high, low)

        # 2. Resting bracket / trailed stop / TP fills (stop checked first).
        fill = self.broker.check_bar_fills(high, low)
        if fill:
            return self._process_exit(fill, now)

        # 3. Scalp the green if it reached the scalp target this bar.
        scalp = self.profit_manager.scalp_signal(position, high, low)
        if scalp.triggered:
            trade = self.broker.close_at_price(scalp.price, reason=scalp.reason)
            if trade:
                return self._process_exit(trade, now)

        # 4. Time stop for stale, never-green trades.
        if self.profit_manager.time_stop(position):
            trade = self.broker.close_at_price(snapshot.last_price, reason="Time stop")
            if trade:
                return self._process_exit(trade, now)

        # 5. LLM thesis-broken exit.
        decision = self._call_llm(ctx, exit_mode=True)
        if decision.action == Direction.CLOSE:
            trade = self.broker.close_at_price(snapshot.last_price, reason="LLM exit")
            if trade:
                return self._process_exit(trade, now)

        self.state_store.log_hold(f"In position: {decision.reasoning}")
        return {"action": "hold_position", "reason": decision.reasoning}

    def _call_llm(self, ctx: PromptContext, exit_mode: bool) -> LLMDecision:
        if self.allowed_direction == Direction.SHORT:
            return self.trader.call_short(ctx, exit_mode=exit_mode)
        return self.trader.call_long(ctx, exit_mode=exit_mode)

    def _process_exit(self, trade: TradeRecord, now: datetime | None = None) -> dict:
        self.risk.record_trade(trade.pnl)
        self.state_store.record_trade(trade)
        self.state_store.state.position = None
        self.state_store.start_cooldown(self.config.engine.cooldown_minutes, now=now)
        logger.info(
            "Exit: %s P&L=$%.2f R=%.2f reason=%s",
            trade.direction.value,
            trade.pnl,
            trade.r_multiple,
            trade.exit_reason,
        )
        return {
            "action": "exit",
            "pnl": trade.pnl,
            "r_multiple": trade.r_multiple,
            "reason": trade.exit_reason,
        }

    def _hard_close(self, reason: str, now: datetime | None = None) -> dict:
        position = self.broker.get_position()
        if not position:
            return {"action": "skip", "reason": reason}
        trade = self.broker.close_position(reason=reason)
        if trade:
            return self._process_exit(trade, now)
        return {"action": "skip", "reason": reason}
