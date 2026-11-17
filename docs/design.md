# Design

How the Capital Drift Monitor works, and the decisions behind it. Measured results are in [results.md](results.md).

## The problem

A homeowners association plans its big repairs in a **reserve study**: every building part (roofs, boilers, paving), its useful life, its replacement cost and the year it should be replaced. The money is spent through **invoices** in the accounting system. The two rarely meet:

- Studies sit in long PDF reports.
- Invoices sit in another system with vague memos.
- Spending is booked to the operating or the reserve fund by hand.

So a part failing early, a replacement put off, or a project running over budget shows up late. The same goes for a big job booked to the wrong fund.

## The pipeline

```
reserve study PDFs ─┐
                    ├─► 1. match invoices to parts ─► 2. watch spend against the plan ─► 3. review queue
invoice export ─────┘      (rules, then Claude)          (repair-or-replace warnings)       (people decide)
                                                                   │
                                                                   └─► 4. reserve forecast ─► board view
```

1. **Matching** (`app/domain/matching.py`, `app/llm/invoice_llm.py`)
   - Rules first: vendor trade, words from the study's own component names and locations, contract numbers that link a deposit to its final bill, and the building named in the memo.
   - When no single part clearly wins, the invoice is **unsure**, and only those go to Claude (Opus 5.5, low effort, a JSON schema for the answer).
   - Code, not the model, decides repair or replacement: 15% of the part's inflated replacement cost.
   - The booked fund is never an input. It's compared afterwards to flag spend booked to the wrong fund.
   - Every Claude call is cached by request hash and logged, failures included, so re-scoring costs nothing.
2. **Warnings** (`app/domain/warnings.py`): the history is replayed month by month. Each warning uses only invoices dated on or before the day it fires, and a test checks this.
   - **Failing early:** a Poisson CUSUM on monthly repair *counts*, against a usual rate learned from the portfolio by age. Counts, not dollars, so one large repair doesn't look like a failing part. The threshold was fixed in advance from a simulated false-alarm rate.
   - **Past due:** the planned year plus 90 days has passed with no completed replacement. Completed means half the plan's cost spent within one project.
   - **Over budget:** a project costs more than the plan plus a 15% contingency.
3. **Review queue** (`app/services/review.py`)
   - Warnings and unsure invoices become items. Each item's key is the part and the plan cycle, so a decision survives every rerun.
   - Past-due warnings list **candidate invoices**: unsure ones, or ones matched to the same kind of part in another building. Those are the usual cause of a false "past due".
   - Placing an invoice reruns the warnings at once and reports what cleared.
   - A rerun never undoes a person's confirm or dismiss.
   - Every action goes to an append-only log with the match before and after.
   - A manager's answers live in their own "reviewed" set of matches, so the measured rules + Claude numbers still reproduce.
4. **Forecast** (`app/domain/forecast.py`)
   - It replays each reserve balance, then runs a seeded Monte Carlo over the study's schedule:
     - past-due parts are due now;
     - parts warned as failing early come due within three years;
     - replacement costs vary as much as the portfolio's own finished projects did.
   - The study gives one contribution figure, so flat and rising-with-inflation contributions are both shown.

## Why it's built this way

- **Pure domain code.** Matching, warnings, the forecast and the board's status rule are pure functions over plain values. Nothing in `app/domain` imports the data generator, and a test enforces it. The API and CLI are thin layers over `app/services`.
- **Synthetic data with an answer key.** `app/synth` generates 20 associations near Philadelphia:
  - reserve studies, written as real PDFs and parsed back;
  - ten years of messy invoices;
  - planted problems: early failures, cost overruns, deferred replacements and miscoded spend.

  The answer key never enters the app's database. Only the evaluation code reads it.
- **Honest evaluation.**
  - Rules were tuned on one seed, and other seeds were held out.
  - Scoring rules were written before results were seen.
  - Regression floors in the tests are never lowered.
  - Where a number depends on a choice made after seeing results, [results.md](results.md) says so.
- **Roles.** Board members read; property managers decide; admins can also rebuild the queue. Auth is static demo tokens behind one dependency (`require_roles`), so replacing it with SSO touches one function.

## Stack

| Layer | Choice |
| --- | --- |
| API | FastAPI, Pydantic v2 |
| Data | SQLAlchemy 2, Alembic; SQLite by default, Postgres tested (migrations checked up and down on Postgres 17) |
| Documents | pdfplumber reads the reserve studies; reportlab writes the synthetic ones |
| Model | Anthropic Python SDK, Claude API or Amazon Bedrock |
| UI | React 18, TypeScript, Vite; charts are plain SVG |
| Packaging | Docker images for the API and for the UI behind nginx |

## Known limits

- **All data is synthetic,** and the same author wrote the generator and the code that reads it, so the measured results are optimistic.
- **The forecast's band reflects replacement cost only.** It held the actual balance 27–64% of the time in the backtest, against an 80% target.
- **The forecast ignores the unpaid balance of a project already in progress.**
- **The board's 10% unplaced-invoice rule is a round number, not a tested one.**
- **Demo auth is static tokens.**
