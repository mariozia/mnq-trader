"""DOM scoring and direction block logic."""

from __future__ import annotations

from dom.dom_book import DOMBook
from models import Direction, GateResult


class DOMAnalyzer:
    def __init__(self, book: DOMBook | None = None) -> None:
        self.book = book or DOMBook()

    def get_score(self) -> float:
        return self.book.imbalance

    def check_gate(
        self, direction: Direction, threshold: float = 30.0
    ) -> GateResult:
        score = self.get_score()

        if direction == Direction.LONG and score < -threshold:
            return GateResult(
                passed=False,
                reason=f"DOM blocked LONG: sellers dominate ({score:.1f} < -{threshold})",
            )
        if direction == Direction.SHORT and score > threshold:
            return GateResult(
                passed=False,
                reason=f"DOM blocked SHORT: buyers dominate ({score:.1f} > +{threshold})",
            )
        return GateResult(passed=True, reason=f"DOM clear ({score:.1f})")
