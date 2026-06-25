#!/usr/bin/env python3
"""Analyze a CSV of real trades and report whether they're profitable.

Export your actual fills (from your prop firm, Robinhood, or anywhere) into a
CSV with at least these columns:

    entry_time, exit_time, direction, entry_price, exit_price, size, pnl

Optional but valuable: risk_points, mfe_points, mae_points (max favorable /
adverse excursion). MFE/MAE are what reveal the "goes green fast then fades"
pattern — if average MFE is much larger than your average realized win, your
take-profit is leaving money on the table and a tighter/trailing exit will help.

Usage:
    python analyze.py my_trades.csv
    python analyze.py my_trades.csv --balance 50000
"""

from __future__ import annotations

import argparse
import sys

from analytics.metrics import compute_metrics, format_report
from analytics.trade_log import load_trades_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a trade-log CSV")
    parser.add_argument("csv_path", help="Path to trades CSV")
    parser.add_argument("--balance", type=float, default=50_000.0)
    args = parser.parse_args(argv)

    trades = load_trades_csv(args.csv_path)
    if not trades:
        print("No trades found in CSV.")
        return 1

    report = compute_metrics(trades, starting_balance=args.balance)
    print(format_report(report, title=f"Trade Analysis — {args.csv_path}"))

    # Highlight the take-profit-too-far pattern if present.
    if report.avg_mfe_points > 0 and report.avg_win > 0:
        avg_win_points = report.avg_win / (
            (sum(t.size for t in trades) / len(trades)) * 2.0
        )
        if report.avg_mfe_points > 1.5 * max(avg_win_points, 0.01):
            print(
                "\n  INSIGHT: average MFE (%.1f pts) is much larger than your "
                "average realized win (~%.1f pts)."
                % (report.avg_mfe_points, avg_win_points)
            )
            print(
                "  Your trades go green further than you're capturing — a "
                "trailing stop or scalp-take would likely raise expectancy."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
