# AGENTS.md: Capital Drift Monitor

A demo for FiXA's founding full-stack engineer role: reserve-study and invoice reconciliation with drift detection, built on Tick & Tie's agent runtime. Read [README.md](README.md) and [docs/plan.md](docs/plan.md) first.

The working agreement in the Home Repo (`~/Desktop/claude-home/docs/working-agreement.md`) applies. This file adds:

- **Attribution.** The first commit (`42ced57`) is Shreyash Methi's Tick & Tie code, used with his permission. Keep the credit line at the top of the README. Don't add a LICENSE until he chooses one for his code.
- **Synthetic data only.** Never use FiXA's data or scrape their app. Label generated data as synthetic wherever it appears.
- **Public repo.** It lives at `juyal-devashish/capital-drift` (public since 2026-11-16), so anything committed is visible. Push only when the user asks. Don't deploy until the user says so and the platform is agreed (AWS is the target, since the role asks for it).
- **Checks.** `make test` (pytest and the frontend typecheck) and `make lint` before every commit. Use Python 3.12 in `.venv`; 3.15 can't install `zstandard`.
- **No real model calls in tests.** The LLM path is stubbed in tests. Ask before any run that makes more than about 10 real API calls.
- **Commits.** Commit after each completed step, on `main` until the first feature branch is needed.
