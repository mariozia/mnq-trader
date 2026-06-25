"""Persistent engine state: cooldown, position tracking, hold log."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from models import EngineState, TradeRecord


class StateStore:
    STATE_FILE = "engine_state.json"

    def __init__(self, data_dir: Path | None = None, persist: bool = True) -> None:
        self.persist = persist
        self.data_dir = data_dir or Path(".state")
        self.state = EngineState()
        if self.persist:
            self.data_dir.mkdir(exist_ok=True)
            self._load()

    def _path(self) -> Path:
        return self.data_dir / self.STATE_FILE

    def _load(self) -> None:
        p = self._path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            if data.get("cooldown_until"):
                self.state.cooldown_until = datetime.fromisoformat(data["cooldown_until"])
        except (json.JSONDecodeError, KeyError):
            pass

    def save(self) -> None:
        if not self.persist:
            return
        data = {
            "cooldown_until": (
                self.state.cooldown_until.isoformat()
                if self.state.cooldown_until
                else None
            ),
        }
        self._path().write_text(json.dumps(data, indent=2))

    def is_in_cooldown(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        if self.state.cooldown_until and now < self.state.cooldown_until:
            return True
        return False

    def start_cooldown(self, minutes: int = 15, now: datetime | None = None) -> None:
        base = now or datetime.now()
        self.state.cooldown_until = base + timedelta(minutes=minutes)
        self.save()

    def clear_cooldown(self) -> None:
        self.state.cooldown_until = None
        self.save()

    def log_hold(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.state.hold_log.append(f"[{ts}] {message}")
        if len(self.state.hold_log) > 100:
            self.state.hold_log = self.state.hold_log[-100:]

    def record_trade(self, trade: TradeRecord) -> None:
        self.state.trades_today.append(trade)

    def reset_opposing_signals(self) -> None:
        self.state.opposing_signal_count = 0
        self.state.last_opposing_signal_time = None

    def increment_opposing_signal(self, now: datetime | None = None) -> int:
        now = now or datetime.now()
        if (
            self.state.last_opposing_signal_time
            and (now - self.state.last_opposing_signal_time).total_seconds() > 120
        ):
            self.state.opposing_signal_count = 0
        self.state.opposing_signal_count += 1
        self.state.last_opposing_signal_time = now
        return self.state.opposing_signal_count
