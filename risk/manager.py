"""Daily P&L and trade count gating."""

from __future__ import annotations

from models import AccountState, GateResult


class RiskManager:
    def __init__(self, account: AccountState, max_trades_per_day: int = 4) -> None:
        self.account = account
        self.max_trades_per_day = max_trades_per_day

    def check_can_trade(self) -> GateResult:
        if self.account.daily_pnl <= self.account.max_daily_loss:
            return GateResult(
                passed=False,
                reason=f"Daily loss limit hit: ${self.account.daily_pnl:.2f}",
            )

        if self.account.daily_pnl >= self.account.max_daily_profit:
            return GateResult(
                passed=False,
                reason=f"Daily profit target hit: ${self.account.daily_pnl:.2f}",
            )

        if self.account.trades_today >= self.max_trades_per_day:
            return GateResult(
                passed=False,
                reason=f"Max trades reached: {self.account.trades_today}/{self.max_trades_per_day}",
            )

        return GateResult(passed=True, reason="Risk checks passed")

    def record_trade(self, pnl: float) -> None:
        self.account.daily_pnl += pnl
        self.account.balance += pnl
        self.account.trades_today += 1

    def reset_daily(self) -> None:
        self.account.daily_pnl = 0.0
        self.account.trades_today = 0
