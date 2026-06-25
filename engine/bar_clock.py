"""Wait until the next 5-minute bar close (for paper trading loops)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta


def seconds_until_next_bar(
    bar_minutes: int = 5,
    settle_seconds: int = 5,
    now: datetime | None = None,
) -> float:
    """Seconds to sleep until the next bar boundary + settle buffer."""
    now = now or datetime.now()
    bar_seconds = bar_minutes * 60
    epoch = now.timestamp()
    next_boundary = ((int(epoch) // bar_seconds) + 1) * bar_seconds + settle_seconds
    return max(0.0, next_boundary - epoch)


def wait_for_next_bar(bar_minutes: int = 5, settle_seconds: int = 5) -> None:
    delay = seconds_until_next_bar(bar_minutes, settle_seconds)
    if delay > 0:
        time.sleep(delay)
