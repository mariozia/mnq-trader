"""Save/load trade logs as CSV so real (prop-firm/Robinhood) trades can be
analyzed with the same metrics as the backtester.

This is the bridge between simulation and reality: export your actual fills to a
CSV with these columns and run `python analyze.py your_trades.csv` to get win
rate, profit factor, expectancy, and — crucially — MFE/MAE, which tell you
whether your trades go green fast then fade (the pattern you described).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from models import Direction, TradeRecord

FIELDS = [
    "entry_time",
    "exit_time",
    "direction",
    "entry_price",
    "exit_price",
    "size",
    "pnl",
    "risk_points",
    "mfe_points",
    "mae_points",
    "r_multiple",
    "bars_held",
    "exit_reason",
]


def save_trades_csv(trades: list[TradeRecord], path: str | Path) -> None:
    path = Path(path)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for t in trades:
            writer.writerow(
                {
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "direction": t.direction.value,
                    "entry_price": f"{t.entry_price:.2f}",
                    "exit_price": f"{t.exit_price:.2f}",
                    "size": t.size,
                    "pnl": f"{t.pnl:.2f}",
                    "risk_points": f"{t.risk_points:.2f}",
                    "mfe_points": f"{t.mfe_points:.2f}",
                    "mae_points": f"{t.mae_points:.2f}",
                    "r_multiple": f"{t.r_multiple:.3f}",
                    "bars_held": t.bars_held,
                    "exit_reason": t.exit_reason,
                }
            )


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()


def load_trades_csv(path: str | Path) -> list[TradeRecord]:
    path = Path(path)
    trades: list[TradeRecord] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            direction = row.get("direction", "LONG").upper()
            trades.append(
                TradeRecord(
                    direction=Direction(direction) if direction in Direction.__members__ else Direction.LONG,
                    entry_price=float(row.get("entry_price", 0) or 0),
                    exit_price=float(row.get("exit_price", 0) or 0),
                    size=int(float(row.get("size", 0) or 0)),
                    pnl=float(row.get("pnl", 0) or 0),
                    entry_time=_parse_dt(row.get("entry_time", "")),
                    exit_time=_parse_dt(row.get("exit_time", "")),
                    exit_reason=row.get("exit_reason", ""),
                    risk_points=float(row.get("risk_points", 0) or 0),
                    mfe_points=float(row.get("mfe_points", 0) or 0),
                    mae_points=float(row.get("mae_points", 0) or 0),
                    r_multiple=float(row.get("r_multiple", 0) or 0),
                    bars_held=int(float(row.get("bars_held", 0) or 0)),
                )
            )
    return trades
