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

It writes four CSV files, one reserve study PDF per association (`reserve_studies/A01.pdf` and so on) and `answer_key.json` to `backend/data/synth/`. It loads the CSV files and reads the reserve studies from the PDFs; `--studies csv` reads `reserve_study.csv` instead. It never loads the answer key.

To match invoices with rules, then ask Claude about the ones the rules left unsure:

```bash
cd backend && ../.venv/bin/python -m app.cli match
```

```bash
cd backend && ../.venv/bin/python -m app.cli match-llm --max-calls 10
```

`match-llm` makes live, paid calls (Claude API with `ANTHROPIC_API_KEY` or an `ant auth login` profile, or Amazon Bedrock; see `backend/.env.example`). It stops at `--max-calls` and caches every response under `backend/data/llm_cache/`, so a re-run only pays for invoices it hasn't asked about. `--cached-only` never calls. `score-matches --method combined` scores rules plus Claude.

Repair-or-replace warnings (no API calls):

```bash
cd backend && ../.venv/bin/python -m app.cli warn --method combined
```

```bash
cd backend && ../.venv/bin/python -m app.cli score-warnings --answer-key data/synth/answer_key.json --method combined
```

`warn` replays the matched spend month by month and stores warnings: a part failing early, a replacement past due, or a replacement over budget. `eval-warnings --seeds 11 12 13` scores whole portfolios in memory without touching the database. Results are in [docs/results.md](docs/results.md).

`make test` runs the backend tests and the frontend typecheck. `make dev-backend` and `make dev-frontend` start the API on :8000 and the UI on :5173. The `seed` and `eval-*` targets need Tick & Tie's test corpus (`../finqa-testdata`), which isn't included. They'll be replaced by the synthetic generator described in the plan.
