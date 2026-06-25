# MNQ Trader

LLM-driven directional trading engine for **MNQ futures** on TopstepX.

Three trading modes share the same data pipeline, gate chain, and execution layer — the difference is how the LLM is prompted and how decisions are made.

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

# Run in mock mode (paper trading, no API keys needed)
python main.py --ai dual --cycles 10

# Other modes
python main.py --ai short-only --cycles 5
python main.py --ai long-only --cycles 5
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

## Live Integration

The mock adapters are designed to be swapped for real services:

- **Broker**: Implement `TopstepXBroker` in `execution/broker.py`
- **LLM**: Set `ANTHROPIC_API_KEY` and run with `--live`
- **GEX**: Implement `RobinhoodGEXProvider` in `data/gex_rh.py`
- **DOM**: Wire WebSocket feed in `dom/dom_book.py`

## Disclaimer

This is algorithmic trading software. Use at your own risk. Mock mode is for development and testing only. Past performance does not guarantee future results.
