#!/usr/bin/env python3
"""MNQ LLM-driven directional trading engine CLI."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

from datetime import timedelta

from config import AIMode, AppConfig, DataFeed, ProfitConfig, TradingMode
from engine.directional_engine import DirectionalEngine
from engine.dual_engine import DualEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mnq-trader")


def create_engine(config: AppConfig):
    if config.ai_mode == AIMode.DUAL:
        return DualEngine(config)
    return DirectionalEngine(config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LLM-driven MNQ futures trading engine for TopstepX",
    )
    parser.add_argument(
        "--ai",
        choices=["short-only", "long-only", "dual"],
        default="dual",
        help="Trading mode (default: dual)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=5,
        help="Number of decision cycles to run (default: 5, 0 = run forever)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=2,
        help="Seconds between cycles in demo mode (default: 2)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use seeded trending mock data so trades trigger in testing",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live APIs (requires credentials in .env)",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="Paper trade: real Yahoo NQ data + simulated fills + real Claude",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Paper mode: run cycles immediately (don't wait for 5m bar close)",
    )
    parser.add_argument(
        "--recon-interval",
        type=int,
        default=5,
        help="Blind recon interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run a multi-day backtest and print a profitability report",
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Backtest days (default: 30)"
    )
    # Dynamic exit (profit-taking) controls
    parser.add_argument("--no-breakeven", action="store_true", help="Disable breakeven stop")
    parser.add_argument("--no-trailing", action="store_true", help="Disable trailing stop")
    parser.add_argument("--trail-trigger-r", type=float, default=1.0)
    parser.add_argument("--trail-dist-r", type=float, default=0.75)
    parser.add_argument("--scalp", action="store_true", help="Enable scalp-take exit (grab the green)")
    parser.add_argument("--scalp-r", type=float, default=0.75)
    parser.add_argument("--max-hold-bars", type=int, default=0)

    args = parser.parse_args(argv)

    ai_mode = AIMode(args.ai)
    profit = ProfitConfig(
        breakeven_enabled=not args.no_breakeven,
        trailing_enabled=not args.no_trailing,
        trailing_trigger_r=args.trail_trigger_r,
        trailing_distance_r=args.trail_dist_r,
        scalp_enabled=args.scalp,
        scalp_target_r=args.scalp_r,
        max_hold_bars=args.max_hold_bars,
    )

    if args.backtest:
        from analytics.metrics import format_report
        from backtest import run_backtest

        report, _ = run_backtest(ai_mode, days=args.days, profit=profit)
        print(format_report(report, title=f"{ai_mode.value} — {args.days} days"))
        return 0

    config = AppConfig.from_env(ai_mode=ai_mode)
    config.demo = args.demo and not args.paper
    config.profit = profit
    config.persist_state = not args.demo

    if args.paper:
        config = AppConfig(
            trading_mode=TradingMode.PAPER,
            ai_mode=ai_mode,
            demo=False,
            data_feed=DataFeed.YAHOO,
            gates=config.gates,
            engine=config.engine,
            profit=profit,
            persist_state=True,
            anthropic_api_key=config.anthropic_api_key,
            anthropic_model=config.anthropic_model,
            yahoo_symbol=config.yahoo_symbol,
            paper_journal_path=config.paper_journal_path,
            topstepx_api_key=config.topstepx_api_key,
            topstepx_username=config.topstepx_username,
            discord_webhook_url=config.discord_webhook_url,
        )
    elif args.live:
        config = AppConfig(
            trading_mode=TradingMode.LIVE,
            ai_mode=ai_mode,
            demo=args.demo,
            gates=config.gates,
            engine=config.engine,
            profit=profit,
            anthropic_api_key=config.anthropic_api_key,
            anthropic_model=config.anthropic_model,
            topstepx_api_key=config.topstepx_api_key,
            topstepx_username=config.topstepx_username,
            discord_webhook_url=config.discord_webhook_url,
        )

    engine = create_engine(config)

    logger.info("=" * 60)
    logger.info("MNQ Trader starting")
    logger.info("  Mode: %s", config.ai_mode.value)
    logger.info("  Trading: %s", config.trading_mode.value)
    if config.trading_mode == TradingMode.PAPER:
        logger.info("  Data feed: %s (%s)", config.data_feed.value, config.yahoo_symbol)
        logger.info("  Paper journal: %s", config.paper_journal_path)
    logger.info("  Cycles: %s", "infinite" if args.cycles == 0 else args.cycles)
    logger.info("=" * 60)

    # Preflight: verify Yahoo data loads before entering the loop
    if config.trading_mode == TradingMode.PAPER:
        try:
            snap = engine.pipeline.fetch_snapshot()
            logger.info(
                "Live data OK — %s @ %.2f | trend=%.0f | %d x5m bars",
                engine.pipeline.source,
                snap.last_price,
                snap.context.trend,
                len(snap.bars_5m),
            )
        except Exception as exc:
            logger.error("Failed to fetch live market data: %s", exc)
            return 1

    cycle = 0
    last_recon = time.time()
    # In demo mode, advance a simulated clock by one bar per cycle so the full
    # entry -> manage -> exit lifecycle plays out quickly.
    sim_now = datetime(2025, 1, 6, 8, 30) if args.demo else None
    bar_seconds = config.engine.cycle_seconds * 5  # 5-min bars

    try:
        while True:
            cycle += 1
            if args.demo:
                now = sim_now
                sim_now = sim_now + timedelta(seconds=bar_seconds)
            else:
                now = datetime.now()

            # Blind recon every N seconds
            if time.time() - last_recon >= args.recon_interval:
                snapshot = engine.pipeline.fetch_snapshot(now)
                recon_result = engine.recon.run(snapshot.last_price)
                if recon_result.action:
                    logger.debug("Recon: %s", recon_result.action)
                last_recon = time.time()

            result = engine.run_cycle(now)
            action = result.get("action", "unknown")

            if action == "enter":
                logger.info(
                    ">>> ENTER %s x%d (conf=%s) — %s",
                    result.get("direction"),
                    result.get("size", 0),
                    result.get("confidence"),
                    result.get("reasoning", ""),
                )
            elif action == "reversal":
                logger.info(
                    ">>> REVERSAL %s -> %s x%d (conf=%s)",
                    result.get("from"),
                    result.get("to"),
                    result.get("size", 0),
                    result.get("confidence"),
                )
            elif action == "exit":
                logger.info(
                    ">>> EXIT P&L=$%.2f — %s",
                    result.get("pnl", 0),
                    result.get("reason"),
                )
            elif action in ("hold", "hold_position", "cooldown", "gate_blocked"):
                logger.info(
                    "— %s: %s",
                    action,
                    result.get("reason", ""),
                )
            else:
                logger.debug("Cycle %d: %s", cycle, result)

            acct = engine.account
            pos = engine.broker.get_position()
            pos_str = "FLAT"
            if pos:
                pos_str = f"{pos.direction.value} x{pos.size} @ {pos.entry_price:.2f}"

            logger.info(
                "  [%d] %s | P&L=$%.2f | Trades=%d | %s",
                cycle,
                now.strftime("%H:%M:%S"),
                acct.daily_pnl,
                acct.trades_today,
                pos_str,
            )

            if args.cycles > 0 and cycle >= args.cycles:
                break

            if args.paper and not args.no_wait and args.cycles == 0:
                from engine.bar_clock import wait_for_next_bar

                wait_for_next_bar(bar_minutes=5, settle_seconds=5)
            else:
                time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("Shutting down...")

    logger.info("=" * 60)
    logger.info("Session summary")
    logger.info("  Daily P&L: $%.2f", engine.account.daily_pnl)
    logger.info("  Trades: %d", engine.account.trades_today)
    logger.info("  Balance: $%.2f", engine.account.balance)
    if engine.paper_journal:
        logger.info("  Paper log: %s", engine.paper_journal.summary())
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
