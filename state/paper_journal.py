"""Append-only paper trading journal (CSV)."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from analytics.trade_log import FIELDS, save_trades_csv
from models import TradeRecord


class PaperJournal:
    """Persists paper trades to CSV for later analysis."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(".paper/trades.csv")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.trades: list[TradeRecord] = []
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        try:
            from analytics.trade_log import load_trades_csv

            self.trades = load_trades_csv(self.path)
        except Exception:
            pass

    def record(self, trade: TradeRecord) -> None:
        self.trades.append(trade)
        self._append_row(trade)

    def _append_row(self, trade: TradeRecord) -> None:
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(
                {
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat(),
                    "direction": trade.direction.value,
                    "entry_price": f"{trade.entry_price:.2f}",
                    "exit_price": f"{trade.exit_price:.2f}",
                    "size": trade.size,
                    "pnl": f"{trade.pnl:.2f}",
                    "risk_points": f"{trade.risk_points:.2f}",
                    "mfe_points": f"{trade.mfe_points:.2f}",
                    "mae_points": f"{trade.mae_points:.2f}",
                    "r_multiple": f"{trade.r_multiple:.3f}",
                    "bars_held": trade.bars_held,
                    "exit_reason": trade.exit_reason,
                }
            )

    def export(self, path: Path | None = None) -> Path:
        out = path or self.path
        save_trades_csv(self.trades, out)
        return out

    def summary(self) -> str:
        if not self.trades:
            return "No paper trades yet."
        total = sum(t.pnl for t in self.trades)
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return (
            f"{len(self.trades)} trades | {wins}W | "
            f"net ${total:,.2f} | log: {self.path}"
        )
