# MNQ Trader

LLM-driven directional trading engine for **MNQ futures** on TopstepX.

Three trading modes share the same data pipeline, gate chain, and execution layer — the difference is how the LLM is prompted and how decisions are made.

> **New here / handing this off?** Read **[SETUP.md](SETUP.md)** — a complete,
> zero-context guide to install and run the project, with instructions for
> connecting real Claude and the Topstep broker when you're ready.

## TL;DR (runs with no API keys)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python main.py --ai dual --demo --cycles 30     # watch a simulated trade
python main.py --ai dual --backtest --days 30    # profitability report
python backtest.py --compare-exits --ai dual     # A/B test exits
python analyze.py my_trades.csv                   # analyze YOUR real trades
```

Or use the shortcuts: `make setup`, `make demo`, `make backtest`, `make compare`.

**Status:** mock/demo/backtest/analyze work out of the box. Real Claude needs
`ANTHROPIC_API_KEY` (adapter ready). Live data feed + Topstep order execution
are the two pieces to wire for paper/live trading — see [SETUP.md](SETUP.md) §8–9.

## Modes

| Mode | Flag | Description |
|------|------|-------------|
| Short-only | `--ai short-only` | Bear regime, single LLM, SHORT or HOLD |
| Long-only | `--ai long-only` | Bull regime, single LLM, LONG or HOLD |
| Dual | `--ai dual` | Both prompts in parallel, consensus entry + reversal |

## Architecture

```
TopstepX WebSocket + REST (mock by default)
        │
        ▼
   Bar Builder → Indicators → Market Context Scorer (7 dimensions)
        │
        ▼
   User Prompt → LLM (Mock or Anthropic Claude)
        │
        ▼
   Gate Chain: Confidence → DOM → GEX → Risk Manager
        │
        ▼
   Bracket Order (market entry + SL stop + TP limit)
```

## Quick Start

```bash
cd ~/Projects/mnq-trader

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Demo a full trade lifecycle on seeded data (no API keys needed)
python main.py --ai dual --demo --cycles 20

# Backtest across 30 simulated trading days and print a profitability report
python main.py --ai dual --backtest --days 30

# A/B test exit strategies (far TP vs breakeven+trailing vs scalp)
python backtest.py --compare-exits --ai dual --days 40

# Analyze YOUR real trades (export fills to CSV first)
python analyze.py my_real_trades.csv
```

## Configuration

Copy `.env.example` to `.env` for live mode:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `TRADING_MODE` | `mock` (default) or `live` |
| `ANTHROPIC_API_KEY` | For live Claude Opus decisions |
| `TOPSTEPX_API_KEY` | TopstepX broker credentials |
| `DISCORD_WEBHOOK_URL` | Alerts for blind recon mismatches |

## Gate Chain

All modes pass through the same gates before execution:

1. **Confidence** ≥ 65 (entry) / ≥ 70 (reversal in dual mode)
2. **DOM Gate** — blocks if order book opposes direction (±30 threshold)
3. **GEX Gate** — blocks pinned markets (>$2Bn during RTH), adjusts TP for negative/positive GEX
4. **Risk Manager** — daily P&L limits and max 4 trades/day

## Key Files

| File | Purpose |
|------|---------|
| `engine/directional_engine.py` | Short-only / long-only engine |
| `engine/dual_engine.py` | Dual prompt engine with reversal logic |
| `ai/prompts.py` | System prompts for each mode |
| `ai/trader.py` | LLM integration (mock + Anthropic) |
| `dom/dom_analyzer.py` | DOM scoring and direction blocks |
| `data/gex_rh.py` | GEX provider (mock + Robinhood stub) |
| `gates/chain.py` | Full gate chain |
| `risk/manager.py` | Daily P&L + trade gating |
| `engine/recon.py` | Blind recon every 5 seconds |
| `engine/scheduler.py` | RTH/overnight sizing, hard close |

## Position Lifecycle

```
FLAT → LLM entry signal → Gates pass → Bracket order
  ├── SL fill → 15-min cooldown
  ├── TP fill → 15-min cooldown
  └── LLM exit (thesis broken) or reversal (dual mode)
```

## Dynamic Exits ("take the green while it's there")

A far take-profit lets winners round-trip into losers. The `ProfitManager`
actively manages every open position against its **initial risk (R = entry-to-stop)**:

| Mechanism | Default | What it does |
|-----------|---------|--------------|
| Breakeven stop | +0.5R | Pull stop to entry so a winner can't go red |
| Trailing stop | +1.0R, trail 0.75R | Ratchet the stop behind the best price |
| Scalp take | off (+0.75R) | Immediately market-close to grab quick green |
| Time stop | off | Force-exit a stale, never-green trade |

"Green enough" is expressed as an **R-multiple**, so it scales per trade instead
of being a fixed dollar amount that's too tight on big moves and too loose on small.

```bash
# Tune via CLI
python main.py --backtest --ai dual --scalp --scalp-r 0.75
python main.py --backtest --ai dual --no-trailing --no-breakeven
```

## Measuring Profitability

```bash
# Backtest + export every trade to CSV
python backtest.py --ai dual --days 30 --export trades.csv

# Run the same metrics on your real fills
python analyze.py trades.csv
```

The report shows win rate, **profit factor**, expectancy (in $ and R), max
drawdown, and **MFE/MAE** (max favorable/adverse excursion). MFE vs realized win
is the key diagnostic: if your trades go green far but you capture little, a
trailing or scalp exit will raise expectancy.

> **Important:** the built-in simulator is a *random walk* — it validates the
> mechanics and lets you tune exits, but it has **no real edge**, so absolute
> backtest P&L is not a verdict on your strategy. To measure real profitability,
> feed real historical data + real LLM calls, or paper-trade live (below) and
> analyze the resulting trade log.

### Real-trade CSV format

Minimum columns: `entry_time, exit_time, direction, entry_price, exit_price, size, pnl`.
Optional but valuable: `risk_points, mfe_points, mae_points`.

## Live Integration

The mock adapters are designed to be swapped for real services:

- **Broker**: Implement `TopstepXBroker` in `execution/broker.py`
- **LLM**: Set `ANTHROPIC_API_KEY` and run with `--live`
- **GEX**: Implement `RobinhoodGEXProvider` in `data/gex_rh.py`
- **DOM**: Wire WebSocket feed in `dom/dom_book.py`

## Disclaimer

This is algorithmic trading software. Use at your own risk. Mock mode is for development and testing only. Past performance does not guarantee future results.
