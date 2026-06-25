"""Build bracket orders from LLM decisions."""

from __future__ import annotations

import uuid

from models import BracketOrder, Direction, LLMDecision


def build_bracket(
    decision: LLMDecision,
    direction: Direction,
    size: int,
    entry_price: float,
    adjusted_tp: float | None = None,
) -> BracketOrder:
    sl_points = decision.stop_loss_points
    tp_points = adjusted_tp or decision.take_profit_points

    if direction == Direction.LONG:
        stop_loss = entry_price - sl_points
        take_profit = entry_price + tp_points
    else:
        stop_loss = entry_price + sl_points
        take_profit = entry_price - tp_points

    return BracketOrder(
        direction=direction,
        size=size,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        order_id=str(uuid.uuid4())[:8],
    )
