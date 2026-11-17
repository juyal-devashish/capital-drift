# Capital Drift Monitor

> Agent runtime, review queue and eval harness adapted from [Tick & Tie](https://github.com/shreyashmethi/finqa-platform) by Shreyash Methi, used with permission. The first commit is his code, unchanged. Every later commit is new work.

A capital-planning demo for homeowner associations and property-management portfolios. It reads a reserve study (each major component's useful life, replacement cost and planned year) and a pile of vendor invoices. Then it:

1. **Matches each invoice to a reserve component**, using rules first and an LLM for the rest, with a confidence score and a link back to the source invoice.
2. **Watches each component's spend for drift** with a sequential change-detection test, and flags components that are running ahead of plan, such as a boiler failing years early.
3. **Sends low-confidence matches and drift alerts to a review queue**, where every decision goes into an audit trail.
4. **Forecasts the reserve balance**, with uncertainty bands, so a board can see which communities run short first.

All data is synthetic.

## Status

Week 1 is built (days 1–8 in [docs/plan.md](docs/plan.md)), all on synthetic data:

- **Data:** a generated portfolio of 20 associations, with reserve studies as PDFs and 10 years of invoices.
- **Matching:** every invoice placed against a part of its reserve study, rules first and then Claude.
- **Warnings:** repair-or-replace warnings when spending drifts from the plan.
- **Review queue:** property managers decide each warning, and every decision is logged.
- **Screens:** a board view, the manager's queue, a page per association and a results page.

Measured results and their caveats are in [docs/results.md](docs/results.md). Tick & Tie's financial QA screens are still here for its own roles.

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

Review queue: `sync-queue` reruns the warnings on reviewed matches and updates the queue. Property managers work it through `/api/capital/queue` (decisions) and `/api/capital/invoices/{id}/assignment` (which part an invoice was for). Board members can only read it. The demo tokens are `board-token`, `manager-token` and `admin-token`. `eval-review` measures how much review clears the false alarms (results in [docs/results.md](docs/results.md)).

**Screens.** Load seed 7, match it, raise warnings and build the queue (`synth`, `match`, `match-llm --cached-only` if you have the cache, `warn`, `sync-queue`). Without Claude's cached answers (they stay on the machine that ran them), the queue is rules-only: on seed 7 that's 442 unplaced invoices and 23 warnings, against 175 and 15 with them. Then start the API and the UI and sign in as one of the demo users:

- **Bea (board member):** reads only. She sees which associations are red and why.
- **Max (property manager):** works the review queue.
- **Adam (admin):** sees both the capital screens and Tick & Tie's screens.

`results --answer-key data/synth/answer_key.json` rewrites `backend/results/capital_results.json`, the file the results page shows.

`make test` runs the backend tests and the frontend typecheck. `make dev-backend` and `make dev-frontend` start the API on :8000 and the UI on :5173. The `seed` and `eval-*` targets need Tick & Tie's test corpus (`../finqa-testdata`), which isn't included. They'll be replaced by the synthetic generator described in the plan.
