# Development

How to run, test and change the Capital Drift Monitor. For what it does, see the [README](../README.md); for how it works, [design.md](design.md).

## Run it locally

You need Python 3.12 and Node 18 or later.

```bash
uv venv --seed --python 3.12 .venv && source .venv/bin/activate
```

```bash
make install
```

```bash
make demo
```

`make demo` generates seed 7 and loads it, matches every invoice, raises the warnings and builds the review queue. It makes no API calls. Claude's answers are read from a local cache in `backend/data/llm_cache/`, which isn't in the repo. Without it, the queue is rules-only: on seed 7 that's 442 unplaced invoices and 23 warnings, against 175 and 15 with Claude's answers.

To fill the cache, set `ANTHROPIC_API_KEY` in `backend/.env` (see `backend/.env.example`). Then run `python -m app.cli match-llm --max-calls 450` from `backend/`, which makes about 430 live calls (roughly $1.20).

Then start the API and the UI in two terminals:

```bash
make dev-backend
```

```bash
make dev-frontend
```

Open http://localhost:5173 and sign in as one of the demo users:

- **Bea, board member:** sees which associations are red and why; changes nothing.
- **Max, property manager:** works the review queue.
- **Adam, admin:** everything Max can do, plus rebuilding the queue.

### With Docker

```bash
docker compose up --build
```

```bash
docker compose exec backend python -m app.cli demo
```

Open http://localhost:8080. The image has no Claude cache, so the queue is rules-only.

## How it works

See [design.md](design.md) for the pipeline and the decisions behind it. In short:

- **Matching** (`backend/app/domain/matching.py`, `backend/app/llm/invoice_llm.py`):
  - Rules use the vendor's trade, the study's own component names and locations, contract numbers and the building named in the memo.
  - Claude sees only the invoices left unsure. It never sees the booked fund or the answer key.
  - Every call is cached and logged, failures included.
- **Warnings** (`backend/app/domain/warnings.py`):
  - A month-by-month replay with no lookahead.
  - "Failing early" is a Poisson CUSUM on repair counts. Its threshold was fixed in advance from a simulated false-alarm rate.
- **Review queue** (`backend/app/services/review.py`):
  - Decisions survive reruns.
  - A manager's answers are kept apart from the measured rules + Claude matches.
- **Forecast** (`backend/app/domain/forecast.py`):
  - A seeded Monte Carlo over the study's schedule, adjusted by what the invoices show.
  - It's backtested from 2020 against what followed.

## Commands

Run from `backend/` with the virtualenv active (`python -m app.cli <command>`):

| Command | What it does |
| --- | --- |
| `demo` | Build the demo database in one step (no API calls) |
| `synth --seed N` | Generate a portfolio: CSVs, one reserve-study PDF per association, and `answer_key.json` (never loaded by the app) |
| `match` | Rule-match every invoice |
| `match-llm --max-calls N` | Ask Claude about the unsure invoices; live calls cost money, `--cached-only` never calls |
| `warn --method combined` | Raise warnings from rules + Claude matches |
| `sync-queue` | Rerun warnings on reviewed matches and update the queue |
| `score-matches`, `score-warnings`, `eval-warnings`, `eval-review`, `results` | Offline evaluation against the answer key |
| `export-static` | Write the read-only snapshot the hosted demo serves |

## The hosted demo

The live demo is a read-only snapshot served from GitHub Pages: no server, no API key, nothing to sign in to. To refresh it after changing the data or the app, run these from the repo root:

```bash
cd backend && python -m app.cli export-static
```

```bash
cd frontend && npm run build:static
```

`export-static` writes `frontend/static-demo/demo/`. Every file is a real API response, fetched the way a board member sees it, so the snapshot can't show anything the app wouldn't. `build:static` builds the app to read those files instead of the API. Commit the snapshot, then run **Deploy demo to GitHub Pages** from the Actions tab.

## Development

```bash
make test
```

```bash
make lint
```

`make test` runs the backend tests (none call the network or a paid API) and the frontend typecheck. The database is SQLite by default. Set `CD_DATABASE_URL` for Postgres; migrations run on startup.

```
backend/
  app/domain/     pure logic: matching, warnings, forecast, board status
  app/llm/        Claude invoice matching (cached, budgeted, every attempt logged)
  app/services/   runs the domain logic over the database
  app/api/        FastAPI routes (/api/capital/...)
  app/synth/      synthetic portfolio generator and reserve-study PDFs
  app/evals/      scoring against the answer key
  results/        the results file the Results page shows
  tests/
frontend/src/     React + TypeScript UI
frontend/static-demo/  the hosted demo's read-only snapshot (JSON)
docs/             design, results and this guide
```
