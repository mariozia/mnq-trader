"""Performance metrics for evaluating whether the bot is profitable."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from models import TradeRecord


@dataclass
class PerformanceReport:
    starting_balance: float
    ending_balance: float
    n_trades: int = 0
    wins: int = 0
    losses: int = 0
    scratches: int = 0
    win_rate: float = 0.0
    net_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    avg_r: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_mfe_points: float = 0.0
    avg_mae_points: float = 0.0
    avg_bars_held: float = 0.0
    return_pct: float = 0.0
    by_exit_reason: dict[str, dict] = field(default_factory=dict)


def compute_metrics(
    trades: list[TradeRecord], starting_balance: float = 50_000.0
) -> PerformanceReport:
    report = PerformanceReport(
        starting_balance=starting_balance,
        ending_balance=starting_balance,
    )
    if not trades:
        return report

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    scratches = [t for t in trades if t.pnl == 0]

    report.n_trades = len(trades)
    report.wins = len(wins)
    report.losses = len(losses)
    report.scratches = len(scratches)
    report.win_rate = len(wins) / len(trades) * 100

    report.gross_profit = sum(t.pnl for t in wins)
    report.gross_loss = sum(t.pnl for t in losses)
    report.net_pnl = sum(t.pnl for t in trades)
    report.profit_factor = (
        report.gross_profit / abs(report.gross_loss)
        if report.gross_loss != 0
        else float("inf")
    )

    report.avg_win = report.gross_profit / len(wins) if wins else 0.0
    report.avg_loss = report.gross_loss / len(losses) if losses else 0.0
    report.expectancy = report.net_pnl / len(trades)
    report.avg_r = sum(t.r_multiple for t in trades) / len(trades)

    report.largest_win = max((t.pnl for t in trades), default=0.0)
    report.largest_loss = min((t.pnl for t in trades), default=0.0)

    report.avg_mfe_points = sum(t.mfe_points for t in trades) / len(trades)
    report.avg_mae_points = sum(t.mae_points for t in trades) / len(trades)
    report.avg_bars_held = sum(t.bars_held for t in trades) / len(trades)

    # Equity curve + max drawdown
    equity = starting_balance
    peak = starting_balance
    max_dd = 0.0
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    report.ending_balance = equity
    report.max_drawdown = max_dd
    report.max_drawdown_pct = max_dd / peak * 100 if peak else 0.0
    report.return_pct = (equity - starting_balance) / starting_balance * 100

    # Breakdown by exit reason
    buckets: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        buckets[t.exit_reason].append(t)
    for reason, group in buckets.items():
        report.by_exit_reason[reason] = {
            "count": len(group),
            "pnl": sum(t.pnl for t in group),
            "win_rate": sum(1 for t in group if t.pnl > 0) / len(group) * 100,
        }

    return report


def format_report(report: PerformanceReport, title: str = "Backtest Results") -> str:
    pf = "inf" if report.profit_factor == float("inf") else f"{report.profit_factor:.2f}"
    lines = [
        "",
        "=" * 60,
        f"  {title}",
        "=" * 60,
        f"  Trades:          {report.n_trades}",
        f"  Win rate:        {report.win_rate:.1f}%  ({report.wins}W / {report.losses}L / {report.scratches}BE)",
        f"  Net P&L:         ${report.net_pnl:,.2f}",
        f"  Return:          {report.return_pct:+.2f}%  (${report.starting_balance:,.0f} -> ${report.ending_balance:,.2f})",
        f"  Profit factor:   {pf}",
        f"  Expectancy:      ${report.expectancy:,.2f}/trade   ({report.avg_r:+.2f}R avg)",
        f"  Avg win:         ${report.avg_win:,.2f}",
        f"  Avg loss:        ${report.avg_loss:,.2f}",
        f"  Largest win:     ${report.largest_win:,.2f}",
        f"  Largest loss:    ${report.largest_loss:,.2f}",
        f"  Max drawdown:    ${report.max_drawdown:,.2f}  ({report.max_drawdown_pct:.1f}%)",
        f"  Avg MFE/MAE:     {report.avg_mfe_points:.1f} / {report.avg_mae_points:.1f} pts",
        f"  Avg hold:        {report.avg_bars_held:.1f} bars",
        "-" * 60,
        "  Exits by reason:",
    ]
    for reason, stats in sorted(
        report.by_exit_reason.items(), key=lambda kv: kv[1]["pnl"], reverse=True
    ):
        lines.append(
            f"    {reason:<22} {stats['count']:>3}x  "
            f"${stats['pnl']:>10,.2f}  ({stats['win_rate']:.0f}% win)"
        )
    lines.append("=" * 60)
    return "\n".join(lines)
