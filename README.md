# Capital Drift Monitor

> Agent runtime, review queue and eval harness adapted from [Tick & Tie](https://github.com/shreyashmethi/finqa-platform) by Shreyash Methi, used with permission. The first commit is his code, unchanged. Every later commit is new work.

A capital-planning demo for homeowner associations and property-management portfolios. It reads a reserve study (each major component's useful life, replacement cost and planned year) and a pile of vendor invoices. Then it:

1. **Matches each invoice to a reserve component**, using rules first and an LLM for the rest, with a confidence score and a link back to the source invoice.
2. **Watches each component's spend for drift** with a sequential change-detection test, and flags components that are running ahead of plan, such as a boiler failing years early.
3. **Sends low-confidence matches and drift alerts to a review queue**, where every decision goes into an audit trail.
4. **Forecasts the reserve balance**, with uncertainty bands, so a board can see which communities run short first.

All data is synthetic.

## Status

**Scaffold only.** The code is still Tick & Tie's financial-reconciliation app; nothing FiXA-specific is built yet. [docs/plan.md](docs/plan.md) lists which parts stay, which get replaced and what's new.

Tick & Tie's original README, including its results on its own synthetic corpus, is in [docs/tick-and-tie-README.md](docs/tick-and-tie-README.md). Those numbers belong to Tick & Tie and are not results for this project.

## Run it

You need Python 3.11 to 3.13 (on 3.15, `zstandard` has no wheel yet) and Node 18+.

```bash
uv venv --python 3.12 .venv
```

```bash
cd backend && uv pip install --python ../.venv/bin/python -e ".[dev]"
```

```bash
cd frontend && npm install
```

```bash
make test
```

To generate the synthetic portfolio and load it into the app database:

```bash
cd backend && ../.venv/bin/python -m app.cli synth --seed 7
```

It writes four CSV files and `answer_key.json` to `backend/data/synth/` and loads only the CSV files.

`make test` runs the backend tests and the frontend typecheck. `make dev-backend` and `make dev-frontend` start the API on :8000 and the UI on :5173. The `seed` and `eval-*` targets need Tick & Tie's test corpus (`../finqa-testdata`), which isn't included. They'll be replaced by the synthetic generator described in the plan.
