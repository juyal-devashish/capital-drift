# AGENTS.md: Capital Drift Monitor

Checks a homeowners association's spending against its reserve study: invoice matching, repair-or-replace warnings, a review queue and a reserve forecast, on synthetic data. Read [README.md](README.md), then [docs/design.md](docs/design.md) and [docs/results.md](docs/results.md).

Rules for anyone (person or agent) changing this repo:

- **Synthetic data only.** Never use real association data or scrape anyone's app. Label generated data as synthetic wherever it appears, in the UI and in docs.
- **The answer key stays offline.** The app never loads `answer_key.json`. Only `app/evals`, the tests and the `score-*`, `eval-*` and `results` commands read it.
- **Public repo.** It lives at `juyal-devashish/capital-drift`, so anything committed is visible. Push only when the user asks. Don't deploy anywhere without the user's go-ahead.
- **Checks.** `make test` (pytest and the frontend typecheck) and `make lint` before every commit. Use Python 3.12 in `.venv`.
- **No real model calls in tests.** The Claude path is stubbed in tests. Ask before any run that makes more than about 10 real API calls; `demo` and `match-llm --cached-only` never call the API.
- **Numbers don't move quietly.** Regression floors in the tests must not be lowered to make a change pass. Results in `docs/results.md` and `backend/results/capital_results.json` come from the commands they cite; regenerate them rather than editing by hand.
- **Commits.** Commit after each completed step, with the checks green.
