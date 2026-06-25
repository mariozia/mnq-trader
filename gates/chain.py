"""Shared gate chain: confidence -> DOM -> GEX -> risk."""

from __future__ import annotations

from datetime import datetime

import pytz

from config import GateConfig
from dom.dom_analyzer import DOMAnalyzer
from models import Direction, GateResult, LLMDecision, MarketSnapshot
from risk.manager import RiskManager

CT = pytz.timezone("America/Chicago")


class GateChain:
    def __init__(
        self,
        config: GateConfig,
        dom_analyzer: DOMAnalyzer,
        risk_manager: RiskManager,
    ) -> None:
        self.config = config
        self.dom = dom_analyzer
        self.risk = risk_manager

    def evaluate_entry(
        self,
        decision: LLMDecision,
        snapshot: MarketSnapshot,
        allowed_direction: Direction | None = None,
    ) -> GateResult:
        if decision.action == Direction.HOLD:
            return GateResult(passed=False, reason="LLM says HOLD")

        direction = decision.action

        if allowed_direction and direction != allowed_direction:
            return GateResult(
                passed=False,
                reason=f"Direction gate: {direction.value} blocked (mode={allowed_direction.value})",
            )

        if decision.confidence < self.config.min_confidence_entry:
            return GateResult(
                passed=False,
                reason=f"Low confidence: {decision.confidence} < {self.config.min_confidence_entry}",
            )

        if decision.stop_loss_points <= 0 or decision.take_profit_points <= 0:
            return GateResult(passed=False, reason="Invalid SL/TP points")

        rr = decision.take_profit_points / decision.stop_loss_points
        if rr < self.config.min_rr_ratio:
            return GateResult(
                passed=False,
                reason=f"R:R too low: {rr:.2f} < {self.config.min_rr_ratio}",
            )

        dom_result = self.dom.check_gate(direction, self.config.dom_threshold)
        if not dom_result.passed:
            return dom_result

        gex_result = self._gex_gate(direction, snapshot, decision.take_profit_points)
        if not gex_result.passed:
            return gex_result

        risk_result = self.risk.check_can_trade()
        if not risk_result.passed:
            return risk_result

        return GateResult(
            passed=True,
            reason="All gates passed",
            adjusted_tp=gex_result.adjusted_tp or decision.take_profit_points,
        )

    def evaluate_reversal(
        self,
        decision: LLMDecision,
        snapshot: MarketSnapshot,
        consecutive_count: int,
    ) -> GateResult:
        if decision.confidence < self.config.min_confidence_reversal:
            return GateResult(
                passed=False,
                reason=f"Reversal confidence too low: {decision.confidence}",
            )

        required = 2  # from config, passed by caller
        if consecutive_count < required:
            return GateResult(
                passed=False,
                reason=f"Anti-flip: {consecutive_count}/{required} consecutive signals",
            )

        return self.evaluate_entry(decision, snapshot)

    def _gex_gate(
        self,
        direction: Direction,
        snapshot: MarketSnapshot,
        tp_points: float,
    ) -> GateResult:
        now = snapshot.timestamp
        if now.tzinfo is None:
            now = CT.localize(now)
        else:
            now = now.astimezone(CT)

        hour = now.hour + now.minute / 60
        in_rth = 8.5 <= hour < 15.0  # 8:30-15:00 CT

        gex = snapshot.gex_bn

        if in_rth and gex > self.config.gex_pinned_threshold_bn:
            return GateResult(
                passed=False,
                reason=f"GEX pinned: ${gex:.2f}Bn > ${self.config.gex_pinned_threshold_bn}Bn",
            )

        adjusted_tp = tp_points
        if gex < 0:
            adjusted_tp = tp_points * self.config.gex_tp_amplify
        elif gex > 0:
            adjusted_tp = tp_points * self.config.gex_tp_dampen

        return GateResult(passed=True, reason=f"GEX clear (${gex:.2f}Bn)", adjusted_tp=adjusted_tp)
