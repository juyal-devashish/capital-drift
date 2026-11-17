# Results

**All numbers here are on synthetic data.** The same person wrote the generator and the rules, so treat them as optimistic. They show the pipeline works end to end and where it struggles. They say nothing yet about real invoices.

## 1. Invoice matching: rules only (2026-11-16)

Each invoice is labelled routine upkeep, a repair to a reserve component, or part of a component's replacement, and given a component. If no single component clearly wins, it's labelled **unsure** and goes to the Claude step (section 2).

The rules use only what a client hands over: vendor name, memo, amount, date, and the reserve study's component names and locations. They don't look at the fund an invoice was booked to; that's compared afterwards to flag spend booked to the wrong fund. Their vocabulary comes from component names plus a short generic list of maintenance terms, not from the generator's word lists.

The rules were tuned on seed 7. Seeds 11 to 13 are held out: the rules never saw them before these numbers were taken.

| Seed | Invoices | Coverage | Component accuracy | Precision on decided | Dollar-weighted | Routine | Repairs | Replacements | Wrong-fund flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 (tuned) | 3,749 | 88.2% | 86.7% | 98.3% | 92.8% | 100.0% | 64.4% | 95.0% | 71/80 (2 wrong) |
| 11 | 3,787 | 87.1% | 85.5% | 98.2% | 90.6% | 100.0% | 63.7% | 89.4% | 75/86 (0 wrong) |
| 12 | 3,650 | 89.1% | 88.2% | 99.0% | 94.6% | 100.0% | 70.2% | 95.2% | 83/98 (0 wrong) |
| 13 | 3,810 | 86.7% | 84.9% | 98.0% | 90.8% | 100.0% | 62.1% | 92.4% | 80/90 (0 wrong) |

**How to read it:**

- **Coverage:** the share of invoices the rules decided (not unsure).
- **Component accuracy (the headline):** correct component, or correctly routine, over *all* invoices. Unsure counts as wrong.
- **Precision on decided:** the same, over decided invoices only. When the rules commit, they're right about 98% of the time.
- **Dollar-weighted:** accuracy weighted by invoice amount. Replacement projects are few but hold most of the money.
- **Routine, Repairs, Replacements:** component accuracy within each true type.
- **Wrong-fund flags:** invoices whose true fund differs from the fund they were booked to, and how many the rules flagged. Most come from the planted miscoded projects and from partial repairs booked to reserve.

**Where the rules give up:** about a third of repairs end up unsure.

- Some memos use trade jargon not in the generic list ("efflorescence", "ridge cap", "anode rod").
- Some say nothing useful ("Labor and materials per ticket").
- Some can't tell two look-alike parts apart without a building ("rotted deck board" at an association with six decks).

That's the AI step's job.

**Work type is not a headline.** Once the component is right, the 15%-of-replacement-cost rule separates repairs from replacements almost by construction. That includes the 147 deliberately ambiguous partial repairs on seed 7: 124 are labelled repair, and 123 carry a "wording says replacement" flag for review.

**Regression floors** in `backend/tests/test_matching.py` hold these numbers for seeds 7 and 11. They must not be lowered to make a change pass.

**Reproduce:**

```bash
cd backend && ../.venv/bin/python -m app.cli synth --seed 7
```

```bash
cd backend && ../.venv/bin/python -m app.cli match
```

```bash
cd backend && ../.venv/bin/python -m app.cli score-matches --answer-key data/synth/answer_key.json
```

## 2. Invoice matching: rules, then Claude for the leftovers (2026-11-16)

Claude Opus 5.5 (low effort, Claude API) was asked only about the 442 invoices the rules left unsure on seed 7. It picks routine, a component, or unsure. Code checks the component exists, applies the 15% repair/replacement rule, and raises wrong-fund flags. Claude never sees the booked fund or the answer key. Scoring rules are unchanged from section 1.

| Seed 7 | Coverage | Component accuracy | Precision on decided | Dollar-weighted | Repairs | Replacements | Wrong-fund flags |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Rules only | 88.2% | 86.7% | 98.3% | 92.8% | 64.4% | 95.0% | 71/80 (2 wrong) |
| Rules + Claude | **95.3%** | **93.3%** | 97.9% | **97.2%** | **81.9%** | **98.1%** | **80/80** (2 wrong) |

**The run:**

- 442 invoices asked: 432 live calls plus 10 from the trial cache.
- Outcomes: 267 answered, 175 left unsure by Claude. No errors, refusals, invalid answers or truncations.
- Tokens: 41.7k input and 35.9k output; 534.6k input tokens served from the prompt cache, with 23.9k written to it.
- Estimated cost: **$1.22** at list price.
- Each call took about 2 seconds.

**Claude's own answers:** 247 of 267 right (92.5%). All 20 misses fall into two groups:

- **8 memos name the wrong building.** These are the generator's planted data-entry errors. Claude followed the memo, as any reader would, and the rules miss these too. Nothing on the invoice could reveal them.
- **12 are "mulch top-up".** The answer key files them under playground equipment, while Claude calls them routine grounds upkeep. That's a labelling judgement in the generator, not a clear mistake. They're still counted as wrong, because the scoring rules were set before the results.

**Still unsure after both steps:** 175 invoices (172 repairs, 3 replacements), mostly memos that say nothing ("Labor and materials per ticket"), or a part with look-alikes in several buildings and no building named. These go to the review queue (section 4).

**Caveats:** this is one seed. Claude isn't fully consistent at low effort: in the 10-call trial, the same memo ("coping stone") was matched once and left unsure once. The responses are cached in `backend/data/llm_cache/` (git-ignored), so re-scoring costs nothing.

**Reproduce** (live calls cost money; cached answers are reused):

```bash
cd backend && ../.venv/bin/python -m app.cli match-llm --max-calls 450
```

```bash
cd backend && ../.venv/bin/python -m app.cli score-matches --answer-key data/synth/answer_key.json --method combined
```

## 3. Repair-or-replace warnings (2026-11-17)

The app replays ten years of matched spend month by month, part by part, and raises three kinds of warnings. Each one uses only invoices dated on or before the day it fires, and a test checks this.

- **Failing early:** repairs are arriving much faster than usual for a part this age, while the plan doesn't replace it until more than a year out. This is a Poisson CUSUM (a running log-likelihood-ratio test) on monthly repair *counts*, tuned to detect a 4× rise. It counts jobs rather than dollars, because one big partial repair shouldn't look like a failing part. The usual rate is learned from the portfolio, pooled by age as a share of useful life, using only the months seen so far.
- **Overdue:** the planned replacement year has passed, plus 90 days for final invoices, and no completed replacement has been found. A replacement counts as completed once it has cost half the plan. A deposit alone doesn't count.
- **Over budget:** a replacement project has cost more than the plan's inflated cost plus a 15% contingency.

**The threshold was set before scoring any planted event.** It came from simulating healthy parts at 0.5 repairs a year: at a CUSUM threshold of 6, one runs about 950 years per false alarm. A 20-association portfolio is about 2,500 watched component-years, so that predicts 2 or 3 false failing-early warnings if the learned baseline were exact. The scoring rules in `backend/app/evals/warnings.py` were written before the first run.

**Miscoded replacements are out of scope here.** Those are replacements booked to the operating fund, and the wrong-fund flags from matching already catch them (80/80 on seed 7).

| Seed, labels | Early failures caught | Before the emergency replacement | Median delay (days) | Deferred caught | Delay | Cost overruns caught | Delay | False alarms | Per 100 component-years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7, perfect labels | 5/5 | 5/5 | 479 | 3/3 | 90 | 4/4 | 171 | 1 (1 failing early) | 0.04 |
| 7, rules | 4/5 | 4/5 | 584 | 3/3 | 90 | 4/4 | 171 | 12 (7 overdue, 4 failing early, 1 over budget) | 0.48 |
| 7, rules + Claude | 4/5 | 4/5 | 440 | 3/3 | 90 | 4/4 | 171 | 4 (2 overdue, 1 failing early, 1 over budget) | 0.16 |
| 11, perfect labels | 2/5 | 2/5 | 411 | 3/3 | 90 | 4/4 | 203 | 1 | 0.04 |
| 12, perfect labels | 5/5 | 5/5 | 433 | 3/3 | 90 | 4/4 | 238 | 1 | 0.04 |
| 13, perfect labels | 5/5 | 5/5 | 453 | 3/3 | 90 | 4/4 | 207 | 2 | 0.08 |
| 11, rules | 1/5 | 1/5 | 627 | 3/3 | 90 | 4/4 | 203 | 21 (18 overdue) | 0.82 |
| 12, rules | 4/5 | 4/5 | 459 | 3/3 | 90 | 4/4 | 238 | 10 (8 overdue) | 0.41 |
| 13, rules | 3/5 | 3/5 | 351 | 3/3 | 90 | 4/4 | 207 | 12 (8 overdue) | 0.47 |

"Perfect labels" feeds the detector the answer key's own matches, which shows the detector alone. Seeds 11–13 have rules-only matches, since Claude was run only on seed 7. Running it on the other seeds would take about 1,300 more API calls, which haven't been made.

**How to read it:**

- **Delay:** days from the event's onset to the warning. For an early failure, onset is the first failing repair. For a deferred replacement, it's 31 December of the planned year. For a cost overrun, it's 1 January of the planned year, so that delay includes waiting for the project to be billed.
- **Before the emergency replacement:** this column equals "caught" by construction, since the failing repairs stop at the emergency replacement and the detector resets there. The informative number is the lead time: 174–613 days on seed 7 with rules + Claude. That's the window in which a board can still plan the replacement instead of paying for an emergency.
- **False alarms** are any warning not credited to a planted event.

**What the numbers say:**

- **Deferred work and overruns are easy once the replacement invoices are matched.** All 28 across the four seeds were caught, with every kind of label: deferred work 90 days after the year ends, overruns on the invoice that crossed the contingency.
- **Early failures are slower.** With perfect labels the detector caught 17 of 20, about 13–16 months after onset (median 411–479 days by seed). The 3 misses on seed 11 failed fast: 3–5 failing repairs before an emergency replacement 17–18 months after onset. That's too few jobs for this threshold. Lowering it is a real trade-off, as the table below shows, so the threshold chosen in advance stays. With rules-only labels on the held-out seeds, it caught 8 of 15, at a median of about 16 months.
- **Most false alarms come from matching, not the detector.** Every overdue false alarm on seeds 7 and 11 (rules) is a real replacement whose invoices were left unsure, or were matched to the same kind of part in a sibling building. A boiler replaced in Bldg A but matched to Bldg B shows up twice: A looks overdue and B looks over budget. Claude's answers cut seed 7's false alarms from 12 to 4. The leftover unsure replacement invoices are what the review queue (section 4) surfaces next to each overdue warning.
- **One early failure was missed because of the matching labels.** It's the playground on seed 7, which the detector catches with perfect labels. Of its 9 failing repairs, Claude placed 4 on the playground and called 3 "mulch top-ups" routine grounds upkeep (see section 2). The rules put the other 2, memos naming both the playground and the fence, on the fence. Four jobs over 14 months weren't enough to fire.

**Threshold trade-off** (pooled held-out seeds 11–13, 15 early failures). The default of 6 was not picked from this table.

| Threshold | Perfect labels: caught | Median delay | False failing-early warnings | Rules: caught | Median delay | False failing-early warnings |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 13/15 | 216 | 41 | 10/15 | 198 | 48 |
| 5 | 13/15 | 392 | 15 | 9/15 | 433 | 18 |
| 6 (default) | 12/15 | 453 | 4 | 8/15 | 484 | 7 |

**Caveats:**

- The planted early-failure signal is about 10–20 times the normal repair rate, so high detection with perfect labels is expected by construction.
- There are 12 in-scope events per seed, so each rate rests on very few cases.
- The fixed settings are round numbers, not fitted, but each sits in a gap the generator creates:
  - The 15% contingency: normal projects run at most 12% over the plan and overruns at least 17% over.
  - The 50% completion share: deposits are 30–40% and partial repairs under 15%.
  - The 180-day project gap: the generator's longest project spans about 135 days.
  - The 90-day grace: final invoices land at most about two weeks into the next year.

  Real projects will be messier on all four.

**Reproduce** (no API calls; Claude's matches come from the cache):

```bash
cd backend && ../.venv/bin/python -m app.cli warn --method combined
```

```bash
cd backend && ../.venv/bin/python -m app.cli score-warnings --answer-key data/synth/answer_key.json --method combined
```

```bash
cd backend && ../.venv/bin/python -m app.cli eval-warnings --seeds 11 12 13 --labels rules
```

## 4. Review queue (2026-11-17)

Warnings and unsure invoices land in one review queue. Property managers (and admins) confirm or dismiss a warning, or say which part an invoice was for. Board members can only read. Every action goes to an append-only log with the user, the role and the match before and after. Changes made automatically by a rerun are logged under the user "system".

An assignment reruns the warnings straight away. A warning that no longer applies is marked resolved-by-rerun, and the response says what changed. A warning a person has confirmed or dismissed is never changed by a rerun. A full sync of seed 7's queue takes about a second.

On seed 7 the queue starts with 15 warnings and 175 unsure invoices. Next to each overdue warning it lists **candidate invoices**: invoices that might be the missing replacement. That rule was written before it was measured:

- the invoice is from the same association;
- it's dated from the year before the planned year up to the day the warning fired;
- it's at least 15% of the part's cost;
- and it's either unsure, or matched to a part with the same name elsewhere (a look-alike in another building).

**How much review it takes.** A simulated property manager opens each overdue warning and assigns its candidates to their true parts from the answer key. Code applies the 15% rule, and the warnings rerun. This is an **upper bound**, because a real reviewer can be wrong or skip invoices.

| Seed, labels | Invoices reviewed | False alarms before → after | Overdue false alarms after | Planted problems caught (before = after) | Detections lost |
| --- | --- | --- | --- | --- | --- |
| 7, rules + Claude | 8 | 4 → 1 | 0 | 11/12 | none |
| 7, rules | 17 | 12 → 4 | 0 | 11/12 | none |
| 11, rules | 46 | 21 → 2 | 0 | 8/12 | none |
| 12, rules | 13 | 10 → 2 | 0 | 11/12 | none |
| 13, rules | 35 | 12 → 3 | 0 | 10/12 | none |

**What it shows:**

- **Looking only at the candidates beside each overdue warning cleared every false overdue and over-budget warning**, on every seed. No planted problem stopped being caught. The cost was 8 invoices on seed 7 with Claude's matches, and 13–46 per seed with rules alone, out of roughly 400–510 unsure invoices.
- The over-budget false alarms clear as a side effect. A boiler replaced in Bldg A but matched to Bldg B produces two warnings, and fixing the match removes both.
- **What's left is failing-early false alarms (1–4 per seed), and most of them come from matching too, just less directly.**
  - 7 of the 11 across these seeds don't fire with perfect labels, even though every repair behind them is matched to the right part.
  - The cause is the learned baseline. The rules give a part to only 933 of seed 7's 1,366 repairs, so the "usual" repair rate comes out about a third too low, and ordinary parts look busy.
  - Working the unsure invoices in the queue, not just the overdue candidates, should raise the baseline and clear some of them. That hasn't been measured.
  - The other 4 also fire with perfect labels. Those are the detector's own false alarms, which a property manager dismisses with a comment the log keeps.
- **Clean held-out seeds are 12 and 13.** Seed 11's false alarms were inspected while building the warnings, before the candidate rule was written, so it isn't fully held out.

The section 2–3 numbers still reproduce. A reviewer's answers go into a separate "reviewed" set of matches, used only by the queue and its warnings. "Combined" stays rules + Claude.

**Reproduce** (no API calls):

```bash
cd backend && ../.venv/bin/python -m app.cli sync-queue
```

```bash
cd backend && ../.venv/bin/python -m app.cli eval-review --answer-key data/synth/answer_key.json
```

```bash
cd backend && ../.venv/bin/python -m app.cli eval-review --seeds 12 13
```

## 5. Reserve forecast (2026-11-17)

For each association, the app replays the reserve balance. It starts from the study's starting balance, adds the recommended contribution each year, and subtracts the replacement spend found. It then runs 500 seeded simulations of the next ten years over the study's replacement schedule, with three adjustments:

- **Past-due parts** are due now.
- **Parts warned as failing early** come due within three years.
- **Replacement costs** vary as much as this portfolio's own finished projects did. Ratios outside 0.5–2× are treated as matching errors and left out.

The board lists who runs short first. Each association page charts the balance so far and the forecast.

**The study doesn't say whether contributions rise**, so both cases are shown:

- **Flat:** the study's figure every year.
- **Rising:** that figure grown at the study's inflation rate.

The synthetic study gives one contribution figure and an inflation rate for costs. One sentence I read in [CAI's explanation of its reserve study standards](https://www.caionline.org/getmedia/7b5f1422-d10b-4cad-87b7-d1339c0f0ee8/explanation-of-reserve-study-standards-2025-final.pdf) requires a study to disclose the interest and inflation values it uses, "zero or otherwise". I haven't read the standards themselves. The reserve is assumed to earn no interest. A balance below zero is a modelled shortfall: work that would need other money, or would be put off.

**Backtest.** The forecast runs from the end of 2020 using only invoices up to then (rules-only matches), and is compared with the balances that actually followed in 2021–2025. Those actual balances use true replacement spend and the same contribution rule. The scoring rules are in `backend/app/evals/forecast.py`.

The baseline is the plain study schedule: every planned replacement on time, at plan cost. Seeds 14–17 were first run after the forecast was written. Seeds 7 and 11–13 were used while building it.

| Contributions | Seeds | Ran short in 2021–25 | Already short in 2020 | Forecast called (false) | Plain schedule called (false) | Band held the balance |
| --- | --- | --- | --- | --- | --- | --- |
| Flat | 7, 11–13 | 24 | 2 | 22 (6) | 18 (3) | 34–59% |
| Flat | 14–17 (fresh) | 26 | 4 | 24 (5) | 19 (0) | 27–64% |
| Rising | 7, 11–13 | 21 | 2 | 17 (1) | 16 (0) | 34–59% |
| Rising | 14–17 (fresh) | 22 | 4 | 18 (2) | 13 (1) | 27–64% |

**What it shows:**

- **It finds more of the associations that run short than the plain schedule does,** in both contribution modes and on the fresh seeds, at the cost of a few more false calls.
- **The misses are early failures without a warning by 2020.** On seeds 7 and 11–13 with perfect labels, all three misses were early failures that hadn't raised a warning by the end of 2020. Two had started failing in 2019–20.
  - One of them, A09's siding on seed 11, already had its replacement deposit paid in November 2020.
  - The forecast ignores the unpaid balance of a project already in progress. That's a known limit, left unfixed so the fresh-seed numbers stay clean.
- **Most false calls are replacements that were planned but never done.** That was 4 of the 6 on those seeds. There the forecast's "short if the work is done" is right, and the work wasn't done.
- **The band is too narrow and isn't an 80% interval.** It reflects spread in replacement cost only. Early failures and deferrals aren't in it, so it held the actual balance only 27–64% of the time. The page says so.
- **The forecast inherits matching errors, in two ways:**
  - **An unplaced replacement** isn't subtracted from the balance, so today's balance is overstated, and the part looks past due, so its cost lands in 2026 instead. Ridley Creek's Bldg A elevator on seed 7 is an example. Its deposit was placed, but its progress and final invoices ($127,741) are still in the review queue. Placed correctly, its 2025 balance would be about $101k below zero, not the $26,444 shown, and the elevator would no longer be charged again in 2026.
  - **A replacement matched to a look-alike part** is subtracted once, but the real part still looks past due. That cost is counted twice.

**On the seed-7 demo:** 7 of 20 associations are already short at the end of 2025 with flat contributions, and 6 with rising. Within ten years, 19 are short in at least half the runs with flat contributions, and 15 with rising. The generator funds associations at 30–80% of the full amount and sets contributions at 60–110% of need, so heavy shortfalls are partly built into the synthetic data.

**Reproduce:**

```bash
cd backend && ../.venv/bin/python -c "from app.evals.forecast import backtest_seed; print(backtest_seed(14, 'rules', contributions='flat'))"
```
