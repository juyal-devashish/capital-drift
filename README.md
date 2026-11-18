# Capital Drift Monitor

**Is a homeowners association's money going where its reserve plan said it would?**

**[Open the live demo →](https://juyal-devashish.github.io/capital-drift/)** It's read-only and uses made-up data, and a four-step guide walks you through it.

## What it does

An association's reserve plan lists every big building part (roofs, boilers, paving), what it costs to replace and when. The money is actually spent through invoices. This app lines the two up:

1. **Files every invoice under the right part of the plan.** Rules do most of it; Claude handles the vague ones.
2. **Flags drift:** a part failing early, a replacement put off, or a project over budget.
3. **Lets a property manager check each flag** before anything is decided, with the evidence on one page.
4. **Forecasts each reserve fund** ten years ahead, so the board sees who runs short first.

## Results at a glance

The data is made up, with problems planted on purpose, so each step can be scored:

- **93%** of invoices filed under the right part (rules alone: 87%), for $1.22 of AI calls.
- **11 of 12** planted problems caught on the demo portfolio.
- **False alarms down from 4 to 1** after a manager checks 8 suggested invoices.
- **The forecast called 24 of 26** associations that ran short, on data it had never seen (the plan alone: 19).

Full tables and caveats are in [docs/results.md](docs/results.md).

## Run it yourself

You need Python 3.12 and Node 18 or later.

```bash
uv venv --seed --python 3.12 .venv && source .venv/bin/activate
```

```bash
make install && make demo
```

```bash
make dev-backend
```

Then, in a second terminal:

```bash
make dev-frontend
```

Open http://localhost:5173 and sign in as Max (property manager) to work the review queue. Docker, the commands and the tests are in [docs/development.md](docs/development.md). How it works is in [docs/design.md](docs/design.md).
