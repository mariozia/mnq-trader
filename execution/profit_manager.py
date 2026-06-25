"""Dynamic exit management: breakeven, trailing stop, and scalp-take.

This is the answer to "how do I take the green while it's there?" Instead of
relying only on the LLM's far take-profit (which lets winners round-trip into
losers), every open position is actively managed against its own initial risk
(R = entry-to-original-stop distance):

  * Breakeven  — after +0.5R, pull stop to entry so a winner can't go red.
  * Trailing   — after +1R, trail the stop 0.75R behind the best price.
  * Scalp take — optionally hard-close at +0.75R to grab quick green.

"Green enough" is defined as an R-multiple, so it scales per trade rather than
being a fixed dollar amount that's too tight on big moves and too loose on small.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import ProfitConfig
from models import Position


@dataclass
class ScalpSignal:
    triggered: bool
    price: float = 0.0
    reason: str = ""


class ProfitManager:
    def __init__(self, config: ProfitConfig) -> None:
        self.config = config

    def update_trailing(self, pos: Position, high: float, low: float) -> None:
        """Update breakeven + trailing stop based on this bar's range.

        Mutates ``pos.stop_loss`` in place. Broker fill checks then run against
        the (possibly tightened) stop.
        """
        risk = pos.risk_points
        if risk <= 0:
            return

        if pos.is_long:
            pos.max_favorable_price = max(pos.max_favorable_price, high)
            pos.max_adverse_price = min(pos.max_adverse_price, low)
            favorable = pos.max_favorable_price - pos.entry_price
        else:
            pos.max_favorable_price = min(pos.max_favorable_price, low)
            pos.max_adverse_price = max(pos.max_adverse_price, high)
            favorable = pos.entry_price - pos.max_favorable_price

        r_gained = favorable / risk

        # Breakeven: lock entry (+offset) once far enough in profit.
        if (
            self.config.breakeven_enabled
            and not pos.breakeven_moved
            and r_gained >= self.config.breakeven_trigger_r
        ):
            offset = self.config.breakeven_offset_points
            if pos.is_long:
                pos.stop_loss = max(pos.stop_loss, pos.entry_price + offset)
            else:
                pos.stop_loss = min(pos.stop_loss, pos.entry_price - offset)
            pos.breakeven_moved = True

        # Trailing: ratchet the stop behind the best price.
        if self.config.trailing_enabled and r_gained >= self.config.trailing_trigger_r:
            dist = self.config.trailing_distance_r * risk
            if pos.is_long:
                trail = pos.max_favorable_price - dist
                pos.stop_loss = max(pos.stop_loss, trail)
            else:
                trail = pos.max_favorable_price + dist
                pos.stop_loss = min(pos.stop_loss, trail)
            pos.trailing_active = True

    def scalp_signal(self, pos: Position, high: float, low: float) -> ScalpSignal:
        """Return a scalp-close signal if the bar reached the scalp target."""
        if not self.config.scalp_enabled:
            return ScalpSignal(False)

        risk = pos.risk_points
        if risk <= 0:
            return ScalpSignal(False)

        target_move = self.config.scalp_target_r * risk
        if pos.is_long:
            target = pos.entry_price + target_move
            if high >= target:
                return ScalpSignal(True, target, f"Scalp +{self.config.scalp_target_r:.2f}R")
        else:
            target = pos.entry_price - target_move
            if low <= target:
                return ScalpSignal(True, target, f"Scalp +{self.config.scalp_target_r:.2f}R")
        return ScalpSignal(False)

    def time_stop(self, pos: Position) -> bool:
        """True if the position has exceeded max_hold_bars without getting green."""
        if self.config.max_hold_bars <= 0:
            return False
        if pos.bars_held < self.config.max_hold_bars:
            return False
        # Only force-exit a stale trade that isn't already in profit.
        if pos.is_long:
            return pos.max_favorable_price <= pos.entry_price
        return pos.max_favorable_price >= pos.entry_price
