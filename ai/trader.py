"""LLM integration with mock and Anthropic backends."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from ai.prompts import (
    SYSTEM_PROMPT_EXIT_EVALUATION,
    SYSTEM_PROMPT_LONG_ONLY,
    SYSTEM_PROMPT_SHORT_ONLY,
)
from config import AppConfig, TradingMode
from models import Direction, LLMDecision, PromptContext


class TraderBackend(ABC):
    @abstractmethod
    def raw_call(self, system_prompt: str, user_prompt: str) -> LLMDecision:
        ...


class MockTrader(TraderBackend):
    """Rule-based mock that mimics LLM decisions from market context."""

    def raw_call(self, system_prompt: str, user_prompt: str) -> LLMDecision:
        is_exit = "EXIT EVALUATION" in system_prompt
        is_short = "SHORT-ONLY" in system_prompt
        is_long = "LONG-ONLY" in system_prompt

        ctx = _parse_context_scores(user_prompt)
        composite = ctx.get("composite", 0.0)
        trend = ctx.get("trend", 0.0)
        rsi = ctx.get("rsi", 50.0)
        atr = ctx.get("atr", 10.0)

        if is_exit:
            return self._exit_decision(composite, trend)

        if is_short:
            return self._short_entry(composite, trend, rsi, atr)
        if is_long:
            return self._long_entry(composite, trend, rsi, atr)

        return LLMDecision(
            action=Direction.HOLD,
            confidence=30,
            stop_loss_points=0,
            take_profit_points=0,
            reasoning="Unknown prompt mode",
        )

    def _short_entry(
        self, composite: float, trend: float, rsi: float, atr: float
    ) -> LLMDecision:
        if trend < -25 and composite < -15 and rsi > 30:
            conf = min(90, int(50 + abs(trend) * 0.5))
            sl = max(8.0, atr * 1.2)
            tp = sl * 2.0
            return LLMDecision(
                action=Direction.SHORT,
                confidence=conf,
                stop_loss_points=sl,
                take_profit_points=tp,
                reasoning=f"Bearish trend ({trend:.0f}), composite {composite:.0f}, RSI not oversold",
            )
        return LLMDecision(
            action=Direction.HOLD,
            confidence=40,
            stop_loss_points=0,
            take_profit_points=0,
            reasoning="No bearish setup — waiting for rip exhaustion",
        )

    def _long_entry(
        self, composite: float, trend: float, rsi: float, atr: float
    ) -> LLMDecision:
        if trend > 25 and composite > 15 and rsi < 65:
            conf = min(90, int(50 + trend * 0.5))
            sl = max(8.0, atr * 1.2)
            tp = sl * 2.0
            return LLMDecision(
                action=Direction.LONG,
                confidence=conf,
                stop_loss_points=sl,
                take_profit_points=tp,
                reasoning=f"Bullish trend ({trend:.0f}), composite {composite:.0f}, buying dip",
            )
        return LLMDecision(
            action=Direction.HOLD,
            confidence=40,
            stop_loss_points=0,
            take_profit_points=0,
            reasoning="No bullish setup — waiting for dip to support",
        )

    def _exit_decision(self, composite: float, trend: float) -> LLMDecision:
        if abs(composite) > 60 and (
            (trend > 40 and composite < -20) or (trend < -40 and composite > 20)
        ):
            return LLMDecision(
                action=Direction.CLOSE,
                confidence=75,
                stop_loss_points=0,
                take_profit_points=0,
                reasoning="Thesis broken — momentum reversed against position",
                is_exit=True,
            )
        return LLMDecision(
            action=Direction.HOLD,
            confidence=60,
            stop_loss_points=0,
            take_profit_points=0,
            reasoning="Thesis intact — letting brackets work",
            is_exit=True,
        )


class AnthropicTrader(TraderBackend):
    """Live Anthropic Claude integration."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-20250514") -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def raw_call(self, system_prompt: str, user_prompt: str) -> LLMDecision:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text
        return _parse_llm_json(text)


class Trader:
    """Facade for LLM trading decisions."""

    PROMPTS = {
        "short": SYSTEM_PROMPT_SHORT_ONLY,
        "long": SYSTEM_PROMPT_LONG_ONLY,
    }

    def __init__(self, config: AppConfig) -> None:
        if config.trading_mode == TradingMode.LIVE and config.anthropic_api_key:
            self.backend: TraderBackend = AnthropicTrader(
                api_key=config.anthropic_api_key,
                model=config.anthropic_model,
            )
        else:
            self.backend = MockTrader()

    def call_short(self, ctx: PromptContext, exit_mode: bool = False) -> LLMDecision:
        prompt = SYSTEM_PROMPT_SHORT_ONLY
        if exit_mode:
            prompt += SYSTEM_PROMPT_EXIT_EVALUATION
        return self.backend.raw_call(prompt, ctx.to_user_prompt())

    def call_long(self, ctx: PromptContext, exit_mode: bool = False) -> LLMDecision:
        prompt = SYSTEM_PROMPT_LONG_ONLY
        if exit_mode:
            prompt += SYSTEM_PROMPT_EXIT_EVALUATION
        return self.backend.raw_call(prompt, ctx.to_user_prompt())


def _parse_context_scores(user_prompt: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    patterns = {
        "trend": r"Trend:\s*([-\d.]+)",
        "composite": r"Composite:\s*([-\d.]+)",
        "rsi": r"RSI:\s*([-\d.]+)",
        "atr": r"ATR:\s*([-\d.]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, user_prompt)
        if m:
            scores[key] = float(m.group(1))
    return scores


def _parse_llm_json(text: str) -> LLMDecision:
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return LLMDecision(
            action=Direction.HOLD,
            confidence=0,
            stop_loss_points=0,
            take_profit_points=0,
            reasoning=f"Failed to parse LLM response: {text[:200]}",
        )

    data = json.loads(match.group())
    action_str = data.get("action", "HOLD").upper()
    action = (
        Direction(action_str)
        if action_str in Direction.__members__
        else Direction.HOLD
    )
    is_exit = action_str == "CLOSE"

    return LLMDecision(
        action=action,
        confidence=int(data.get("confidence", 0)),
        stop_loss_points=float(data.get("stop_loss_points", 0)),
        take_profit_points=float(data.get("take_profit_points", 0)),
        reasoning=data.get("reasoning", ""),
        is_exit=is_exit or data.get("action", "").upper() == "CLOSE",
    )
