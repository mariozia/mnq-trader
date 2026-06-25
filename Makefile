.PHONY: help setup demo backtest compare analyze verify clean

PY := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "MNQ Trader — common commands"
	@echo "  make setup      Create venv and install dependencies"
	@echo "  make demo       Run a simulated trade lifecycle (dual mode)"
	@echo "  make backtest   Run a 30-day backtest (dual mode)"
	@echo "  make compare    A/B test exit strategies"
	@echo "  make verify     Quick end-to-end smoke test"
	@echo "  make clean      Remove venv and saved state"

setup:
	python3 -m venv .venv
	$(PIP) install -r requirements.txt
	@echo "\nDone. Activate with:  source .venv/bin/activate"

demo:
	$(PY) main.py --ai dual --demo --cycles 30 --interval 0

backtest:
	$(PY) main.py --ai dual --backtest --days 30

compare:
	$(PY) backtest.py --compare-exits --ai dual --days 40

analyze:
	@test -n "$(CSV)" || (echo "Usage: make analyze CSV=path/to/trades.csv" && exit 1)
	$(PY) analyze.py $(CSV)

verify:
	$(PY) main.py --ai short-only --demo --cycles 20 --interval 0
	$(PY) main.py --ai dual --backtest --days 10

clean:
	rm -rf .venv .state
