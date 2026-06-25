# MNQ Trader — Setup & Handoff Guide

This is everything a new person needs to run the project from scratch. No prior
context required. Follow it top to bottom.

> **What this is:** an LLM-driven directional trading engine for **MNQ (Micro
> E-mini Nasdaq-100) futures**, modeled on the TopstepX workflow. It has three
> modes (short-only, long-only, dual), a 7-dimension market-context scorer, a
> gate chain (confidence → DOM → GEX → risk), bracket execution, and a dynamic
> exit layer (breakeven / trailing / scalp). It ships with a **backtester** and
> a **trade analyzer** so you can measure profitability.

---

## 1. Current status — what works now vs. what needs keys

| Capability | Works today? | Needs |
|------------|:---:|-------|
| Simulated demo (full trade lifecycle) | ✅ Yes | nothing |
| Multi-day backtest + profitability report | ✅ Yes | nothing |
| A/B test exit strategies | ✅ Yes | nothing |
| Analyze your real trades from a CSV | ✅ Yes | nothing |
| Rule-based "mock" LLM decisions | ✅ Yes | nothing |
| **Real Claude decisions** | ⚙️ Ready | `ANTHROPIC_API_KEY` |
| **Live market data feed** | ❌ Not built | a data source (see §8) |
| **Real / sim order execution (TopstepX)** | ⚙️ Stub | implement adapter + keys (§9) |

So: **you can fully test, backtest, and tune the system right now with zero
setup.** Real Claude is a one-line env change. Live data + broker execution are
the two pieces to wire when you're ready to paper/live trade (§8–9).

---

## 2. Prerequisites

- **Python 3.11 or newer** (developed on 3.12). Check: `python3 --version`
- **git** (to clone) — optional if you already have the folder
- macOS / Linux / Windows (commands below are macOS/Linux; Windows notes inline)

---

## 3. Install

```bash
# 1) Get the code (or just open the existing folder)
cd ~/Projects/mnq-trader      # or wherever the project lives

# 2) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3) Install dependencies
pip install -r requirements.txt
#   (or, equivalently:  pip install -e .)
```

That's it. Everything below runs without any API keys.

---

## 4. Run it (no keys needed)

### a) Watch a full trade lifecycle on simulated data
```bash
python main.py --ai dual --demo --cycles 30 --interval 0
```
You'll see ENTER → position management → EXIT lines and a session P&L summary.
Try `--ai short-only` and `--ai long-only` too.

### b) Backtest across simulated trading days
```bash
python main.py --ai dual --backtest --days 30
```
Prints win rate, profit factor, expectancy, drawdown, MFE/MAE, and a breakdown
of exits by reason.

### c) Compare exit strategies (the "take the green" question)
```bash
python backtest.py --compare-exits --ai dual --days 40
```
Side-by-side: far-TP-only vs breakeven+trailing vs scalp-take.

### d) Analyze your *real* trades
Export your fills to a CSV with at least these columns:
`entry_time, exit_time, direction, entry_price, exit_price, size, pnl`
(optional but valuable: `risk_points, mfe_points, mae_points`), then:
```bash
python analyze.py my_real_trades.csv
```

> ⚠️ **Read this about the backtester:** the built-in price feed is a *random
> walk* with **no real edge**. It validates the mechanics and lets you tune
> exits, but the absolute backtest P&L is NOT a verdict on the strategy. Real
> profitability can only be judged on **real data + real LLM** or a live paper
> account (§8). The most useful real-world signal is **MFE vs. your realized
> win** from `analyze.py` on your actual trades.

---

## 5. Understanding the report

| Metric | Meaning |
|--------|---------|
| Win rate | % of trades that closed green |
| Profit factor | gross profit ÷ gross loss. >1 is profitable; aim for ≥1.3 |
| Expectancy | average $ (and R) per trade. The number that matters most |
| Max drawdown | largest peak-to-valley equity drop |
| MFE / MAE | max favorable / adverse excursion (how far green / red it went) |

**Key diagnostic:** if average MFE is much bigger than your average win, your
take-profit is too far — money is going green then fading. That's what the
trailing/scalp exits fix.

---

## 6. Tuning the exits ("green enough")

"Green enough" is defined in **R** (R = entry-to-stop distance), so it scales per
trade. Defaults: breakeven at +0.5R, trailing at +1R (trail 0.75R), scalp off.

```bash
# Turn on the scalp-take (grab the quick green) at +0.75R
python main.py --backtest --ai dual --scalp --scalp-r 0.75

# Disable active management to compare against far-TP-only
python main.py --backtest --ai dual --no-trailing --no-breakeven
```
Flags: `--scalp`, `--scalp-r`, `--no-trailing`, `--no-breakeven`,
`--trail-trigger-r`, `--trail-dist-r`, `--max-hold-bars`.

---

## 7. Connecting real Claude (when ready)

The engine already has an Anthropic adapter (`ai/trader.py`). To use real Claude:

```bash
cp .env.example .env
# edit .env:
#   TRADING_MODE=live
#   ANTHROPIC_API_KEY=sk-ant-...
python main.py --ai dual --live --cycles 5
```

If the key is present it calls Claude; otherwise it transparently falls back to
the rule-based mock so nothing breaks.

> **Why not "just use Claude from the chat"?** The bot needs to make an
> autonomous decision on its own schedule (every cycle, potentially 24/5). That
> requires its **own** API key running inside the program — a chat assistant
> can't be the live runtime brain of an unattended trading loop. The mock LLM
> lets you prove out all the plumbing first; the real key is a drop-in swap.

---

## 8. Connecting a live market-data feed (to paper trade)

This is the main piece left to build for live/paper trading. Options:

1. **Your broker's own feed (recommended).** TopstepX/ProjectX, Tradovate demo,
   or NinjaTrader sim provide data *and* execution together — cleanest path.
2. **Free delayed data** (Yahoo `NQ=F`) for non-real-time testing.

Where to wire it: create a feed that returns `Bar` objects and feed it into
`data/pipeline.py` (today the pipeline uses the simulated `BarBuilder`). The
`Bar`/`MarketSnapshot` models in `models.py` define the shape you must produce.

---

## 9. Connecting the broker for real/sim orders (TopstepX)

`execution/broker.py` contains `TopstepXBroker` as a **stub** with the exact
interface the engine expects:

- `place_bracket(order)` — submit market entry + SL + TP
- `get_position()` / `sync_state()` — current position from the exchange
- `check_bracket_fills(price)` — detect SL/TP fills
- `close_at_price(price, reason)` — market close

Implement these against the TopstepX/ProjectX Gateway API (REST for orders +
SignalR/WebSocket for fills), set `TOPSTEPX_API_KEY` / `TOPSTEPX_USERNAME` in
`.env`, and the engine will route to it automatically when `TRADING_MODE=live`.
Until then, the safe mock broker simulates fills locally.

---

## 10. Project structure

```
mnq-trader/
├── main.py                 # CLI entry: demo, --backtest, --live
├── backtest.py             # multi-day backtester + --compare-exits
├── analyze.py              # analyze a CSV of real trades
├── config.py               # all settings (modes, gates, profit/exit config)
├── models.py               # domain models (Bar, Position, TradeRecord, ...)
├── requirements.txt
├── ai/
│   ├── prompts.py          # short/long/exit system prompts
│   └── trader.py           # mock LLM + real Anthropic adapter
├── data/
│   ├── bar_builder.py      # simulated price feed (swap for real data here)
│   ├── indicators.py       # EMA/MACD/RSI/BB/VWAP/ATR/volume profile
│   ├── market_context.py   # 7-dimension context scorer
│   ├── gex_rh.py           # GEX provider (mock + Robinhood stub)
│   └── pipeline.py         # data → indicators → context → snapshot
├── dom/                    # depth-of-market book + analyzer
├── gates/chain.py          # confidence → DOM → GEX → risk gate chain
├── risk/manager.py         # daily P&L + trade-count limits
├── execution/
│   ├── broker.py           # MockBroker (works) + TopstepXBroker (stub)
│   ├── brackets.py         # bracket order builder
│   └── profit_manager.py   # breakeven / trailing / scalp exits
├── engine/
│   ├── directional_engine.py  # short-only / long-only engine
│   ├── dual_engine.py         # dual-prompt consensus + reversal
│   ├── scheduler.py           # RTH/overnight, hard close (DST-safe)
│   └── recon.py               # blind recon / state reconciliation
├── analytics/
│   ├── metrics.py          # performance report
│   └── trade_log.py        # CSV save/load
└── state/store.py          # cooldown + position persistence
```

---

## 11. Troubleshooting

| Problem | Fix |
|---------|-----|
| `command not found: python` | Use `python3`, or activate the venv |
| `ModuleNotFoundError` | Activate venv, then `pip install -r requirements.txt` |
| Demo shows 0 trades | Normal for short runs/regimes; use `--backtest` for volume |
| `anthropic` errors in mock mode | Ignore — mock mode never calls it |
| Want a fresh run | Delete the `.state/` folder |

---

## 12. Risk disclaimer

This is experimental algorithmic-trading software provided as-is. Mock and
backtest modes are for development and education only. Backtest results on
simulated data are **not** predictive of live performance. Trading futures
involves substantial risk of loss. Never run live with money you can't afford to
lose, and validate thoroughly on a paper/sim account first.
