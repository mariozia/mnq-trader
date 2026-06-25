#!/usr/bin/env python3
"""Backtest / paper-trading harness.

Runs an engine over many simulated 5-minute bars across multiple trading days
(RTH only, weekdays), switching market regimes day to day so both long and
short setups appear, then prints a profitability report.

This is how you answer "is my bot actually profitable?" without risking money:
the mock LLM + simulated price feed let you measure win rate, profit factor,
expectancy, and drawdown, and A/B test the dynamic-exit settings.

Usage:
    python backtest.py --ai dual --days 30
    python backtest.py --ai short-only --days 30 --scalp --scalp-r 0.75
    python backtest.py --compare-exits --ai dual --days 30
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from datetime import datetime, timedelta

import pytz

from analytics.metrics import compute_metrics, format_report
from data.feeds.mock import MockDataFeed
from config import AIMode, AppConfig, ProfitConfig, TradingMode
from engine.directional_engine import DirectionalEngine
from engine.dual_engine import DualEngine

CT = pytz.timezone("America/Chicago")

# Day-to-day regime drift (points per 5-min bar). Cycles so the bot sees
# bull trends, bear trends, and chop.
REGIMES = [1.2, -1.2, 0.4, -0.4, 0.8, -0.8, 0.1, -0.1]


def _make_engine(config: AppConfig):
    if config.ai_mode == AIMode.DUAL:
        return DualEngine(config)
    return DirectionalEngine(config)


def _session_timestamps(day: datetime):
    """5-min bar timestamps from 08:30 to 14:55 CT for a given weekday."""
    start = CT.localize(day.replace(hour=8, minute=30, second=0, microsecond=0))
    end = CT.localize(day.replace(hour=14, minute=55, second=0, microsecond=0))
    ts = start
    while ts <= end:
        yield ts
        ts += timedelta(minutes=5)


def _trading_days(n: int):
    """Yield n weekday dates starting from a fixed Monday for reproducibility."""
    day = datetime(2025, 1, 6)  # a Monday
    count = 0
    while count < n:
        if day.weekday() < 5:
            yield day
            count += 1
        day += timedelta(days=1)


def run_backtest(
    ai_mode: AIMode,
    days: int = 30,
    profit: ProfitConfig | None = None,
    starting_balance: float = 50_000.0,
    seed_offset: int = 0,
):
    config = AppConfig(
        trading_mode=TradingMode.MOCK,
        ai_mode=ai_mode,
        demo=True,
        persist_state=False,
        profit=profit or ProfitConfig(),
    )
    engine = _make_engine(config)
    engine.account.balance = starting_balance
    # Loosen the daily profit/loss circuit breakers so the backtest can run a
    # full sample instead of halting after one good/bad day.
    engine.account.max_daily_loss = -1e9
    engine.account.max_daily_profit = 1e9

    for day_idx, day in enumerate(_trading_days(days)):
        engine.reset_for_new_day()
        bias = REGIMES[(day_idx + seed_offset) % len(REGIMES)]
        feed = engine.pipeline.feed
        if isinstance(feed, MockDataFeed):
            feed.bar_builder.set_trend_bias(bias)
        for ts in _session_timestamps(day):
            engine.run_cycle(ts.astimezone())

    trades = engine.state_store.state.trades_today
    return compute_metrics(trades, starting_balance), trades


def _profit_from_args(args) -> ProfitConfig:
    return ProfitConfig(
        breakeven_enabled=not args.no_breakeven,
        trailing_enabled=not args.no_trailing,
        trailing_trigger_r=args.trail_trigger_r,
        trailing_distance_r=args.trail_dist_r,
        scalp_enabled=args.scalp,
        scalp_target_r=args.scalp_r,
        max_hold_bars=args.max_hold_bars,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="MNQ bot backtester")
    parser.add_argument("--ai", choices=["short-only", "long-only", "dual"], default="dual")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--balance", type=float, default=50_000.0)
    parser.add_argument("--no-breakeven", action="store_true")
    parser.add_argument("--no-trailing", action="store_true")
    parser.add_argument("--trail-trigger-r", type=float, default=1.0)
    parser.add_argument("--trail-dist-r", type=float, default=0.75)
    parser.add_argument("--scalp", action="store_true", help="Enable scalp-take exit")
    parser.add_argument("--scalp-r", type=float, default=0.75)
    parser.add_argument("--max-hold-bars", type=int, default=0)
    parser.add_argument(
        "--compare-exits",
        action="store_true",
        help="A/B test exit strategies (far TP vs trailing vs scalp)",
    )
    parser.add_argument("--export", help="Write trade log to this CSV path")
    args = parser.parse_args(argv)

    ai_mode = AIMode(args.ai)

    if args.compare_exits:
        variants = {
            "Far TP only (no active mgmt)": ProfitConfig(
                breakeven_enabled=False, trailing_enabled=False, scalp_enabled=False
            ),
            "Breakeven + Trailing": ProfitConfig(
                breakeven_enabled=True, trailing_enabled=True, scalp_enabled=False
            ),
            "Scalp +0.75R (grab the green)": ProfitConfig(
                breakeven_enabled=True, trailing_enabled=True,
                scalp_enabled=True, scalp_target_r=0.75,
            ),
            "Scalp +0.5R (faster grab)": ProfitConfig(
                breakeven_enabled=True, trailing_enabled=True,
                scalp_enabled=True, scalp_target_r=0.5,
            ),
        }
        print(f"\nA/B test — {ai_mode.value}, {args.days} simulated days\n")
        for name, pc in variants.items():
            report, _ = run_backtest(ai_mode, days=args.days, profit=pc, starting_balance=args.balance)
            print(format_report(report, title=name))
        return 0

    profit = _profit_from_args(args)
    report, trades = run_backtest(ai_mode, days=args.days, profit=profit, starting_balance=args.balance)
    print(format_report(report, title=f"{ai_mode.value} — {args.days} days"))
    if args.export:
        from analytics.trade_log import save_trades_csv

        save_trades_csv(trades, args.export)
        print(f"\nTrade log written to {args.export}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
