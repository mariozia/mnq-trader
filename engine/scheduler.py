"""Trading windows, session detection, and hard close (DST-safe)."""

from __future__ import annotations

from datetime import datetime

import pytz

from models import SessionType

CT = pytz.timezone("America/Chicago")


class Scheduler:
    """RTH vs overnight session detection and trading window gates."""

    RTH_OPEN_HOUR = 8
    RTH_OPEN_MINUTE = 30
    RTH_CLOSE_HOUR = 15
    RTH_CLOSE_MINUTE = 0
    HARD_CLOSE_HOUR = 14
    HARD_CLOSE_MINUTE = 55

    def now_ct(self, now: datetime | None = None) -> datetime:
        if now is None:
            return datetime.now(CT)
        if now.tzinfo is None:
            return CT.localize(now)
        return now.astimezone(CT)

    def session_type(self, now: datetime | None = None) -> SessionType:
        t = self.now_ct(now)
        open_minutes = self.RTH_OPEN_HOUR * 60 + self.RTH_OPEN_MINUTE
        close_minutes = self.RTH_CLOSE_HOUR * 60 + self.RTH_CLOSE_MINUTE
        current = t.hour * 60 + t.minute

        if open_minutes <= current < close_minutes:
            return SessionType.RTH
        return SessionType.OVERNIGHT

    def is_trading_window(self, now: datetime | None = None) -> bool:
        t = self.now_ct(now)
        if t.weekday() >= 5:
            return False
        return True

    def should_hard_close(self, now: datetime | None = None) -> bool:
        t = self.now_ct(now)
        hard = self.HARD_CLOSE_HOUR * 60 + self.HARD_CLOSE_MINUTE
        current = t.hour * 60 + t.minute
        return current >= hard and self.session_type(now) == SessionType.RTH

    def contract_size(self, rth_size: int, overnight_size: int, now: datetime | None = None) -> int:
        if self.session_type(now) == SessionType.RTH:
            return rth_size
        return overnight_size
