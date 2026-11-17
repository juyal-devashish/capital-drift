# Capital Drift Monitor

Is a homeowners association's money going where its reserve study said it would?

The Capital Drift Monitor reads an association's **reserve study** (each building part's useful life, replacement cost and planned year) and its **vendor invoices**. Then it:

1. **Places every invoice against a part of the study.** Rules go first, Claude handles the ones the rules can't place, and code decides repair or replacement and flags spend booked to the wrong fund.
2. **Watches spending against the plan** and raises three warnings, each worded as a repair-or-replace call: a part **failing early**, a replacement **past due**, or a replacement **over budget**.
3. **Puts warnings and unplaced invoices in a review queue.** Property managers decide, every decision is logged, and placing an invoice reruns the warnings at once.
4. **Forecasts each reserve balance** ten years ahead, so the board can see who runs short first.

**All data is synthetic:** 20 made-up associations near Philadelphia, their reserve studies (as PDFs) and ten years of invoices, with planted problems to find.

## Results on synthetic data

Full tables, scoring rules and caveats are in [docs/results.md](docs/results.md). The headlines:

| Step | Result |
| --- | --- |
| Matching, seed 7 | Rules alone place 88% of invoices and are right on 98% of those. Rules + Claude get the right part (or routine) for **93.3%** of all invoices and 97.2% by dollars, for **$1.22** of API calls. |
| Matching, held-out seeds 11–13 | Rules alone: 85–88% right over all invoices. |
| Warnings, held-out seeds 11–13 (rules only) | **21 of 21** deferred replacements and cost overruns caught. 8 of 15 early failures caught, at a median of about 16 months after onset. Most false alarms come from matching, not the detector. |
| Review queue, held-out seed 12 | A simulated manager placing only the candidate invoices beside past-due warnings (13 invoices) cut false alarms from 10 to 2, with no planted problem lost. This is an upper bound. |
| Forecast backtest, fresh seeds 14–17 (flat contributions) | Forecasting from 2020, it called **24 of 26** associations that ran short by 2025 (the plain study schedule called 19), with 5 false calls. |

These are synthetic results, and the same author wrote the generator and the code that reads it, so treat them as optimistic.

## Quick start

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

See [docs/design.md](docs/design.md) for the pipeline and the decisions behind it. In short:

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
docs/             design and results
```
