# Results

**All numbers here are on synthetic data.** The same person wrote the generator and the rules, so treat them as optimistic. They show the pipeline works end to end and where it struggles. They say nothing yet about real invoices.

## Invoice matching: rules only (day 3, 2026-11-16)

Each invoice is labelled routine upkeep, a repair to a reserve component, or part of a component's replacement, and given a component. If no single component clearly wins, it's labelled **unsure** and goes to the AI step on day 4.

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

## Invoice matching: rules, then Claude for the leftovers (day 4, 2026-11-16)

Claude Opus 5.5 (low effort, Claude API) was asked only about the 442 invoices the rules left unsure on seed 7. It picks routine, a component, or unsure. Code checks the component exists, applies the 15% repair/replacement rule, and raises wrong-fund flags. Claude never sees the booked fund or the answer key. Scoring rules are unchanged from day 3.

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

**Still unsure after both steps:** 175 invoices (172 repairs, 3 replacements), mostly memos that say nothing ("Labor and materials per ticket"), or a part with look-alikes in several buildings and no building named. These go to the review queue (day 6).

**Caveats:** this is one seed. Claude isn't fully consistent at low effort: in the 10-call trial, the same memo ("coping stone") was matched once and left unsure once. The responses are cached in `backend/data/llm_cache/` (git-ignored), so re-scoring costs nothing.

**Reproduce** (live calls cost money; cached answers are reused):

```bash
cd backend && ../.venv/bin/python -m app.cli match-llm --max-calls 450
```

```bash
cd backend && ../.venv/bin/python -m app.cli score-matches --answer-key data/synth/answer_key.json --method combined
```

## Repair-or-replace warnings (day 5, 2026-11-17)

The app replays ten years of matched spend month by month, part by part, and raises three kinds of warnings. Each one uses only invoices dated on or before the day it fires, and a test checks this.

- **Failing early:** repairs are arriving much faster than usual for a part this age, while the plan doesn't replace it until more than a year out. This is a Poisson CUSUM (a running log-likelihood-ratio test) on monthly repair *counts*, tuned to detect a 4× rise. It counts jobs rather than dollars, because one big partial repair shouldn't look like a failing part. The usual rate is learned from the portfolio, pooled by age as a share of useful life, using only the months seen so far.
- **Overdue:** the planned replacement year has passed, plus 90 days for final invoices, and no completed replacement has been found. A replacement counts as completed once it has cost half the plan. A deposit alone doesn't count.
- **Over budget:** a replacement project has cost more than the plan's inflated cost plus a 15% contingency.

**The threshold was set before scoring any planted event.** I simulated healthy parts at 0.5 repairs a year and picked the CUSUM threshold (6) at which one runs about 600 years before a false alarm. A 20-association portfolio is about 2,500 watched component-years, so that predicts roughly 4 false failing-early warnings. Scoring rules are in `backend/app/evals/warnings.py`, and they were written before the first run.

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

"Perfect labels" feeds the detector the answer key's own matches, which shows the detector alone. Seeds 11–13 have rules-only matches, since Claude was run only on seed 7. Running it on the other seeds would take about 1,300 more API calls, and I haven't run them.

**How to read it:**

- **Delay:** days from the event's onset to the warning. For an early failure, onset is the first failing repair. For a deferred replacement, it's 31 December of the planned year. For a cost overrun, it's 1 January of the planned year, so that delay includes waiting for the project to be billed.
- **Before the emergency replacement:** in every early failure the warning caught, it fired months before the part had to be replaced in an emergency (174–613 days on seed 7 with rules + Claude). That lead time is when a board can still plan the replacement instead of paying for an emergency.
- **False alarms** are any warning not credited to a planted event.

**What the numbers say:**

- **Deferred work and overruns are easy once the replacement invoices are matched.** All 28 across the four seeds were caught, with every kind of label: deferred work 90 days after the year ends, overruns on the invoice that crossed the contingency.
- **Early failures are slower.** With perfect labels the detector caught 17 of 20, about 14–16 months after onset (median 411–479 days by seed). The 3 misses on seed 11 failed fast: 3–5 failing repairs before an emergency replacement 17–18 months after onset. That's too few jobs for this threshold. Lowering it is a real trade-off, as the table below shows, so I kept the threshold chosen in advance.
- **Most false alarms come from matching, not the detector.** Every overdue false alarm on seeds 7 and 11 is a real replacement whose invoices were left unsure or matched to a look-alike part in another building. A boiler replaced in Bldg A but matched to Bldg B shows up twice: A looks overdue and B looks over budget. Claude's answers cut seed 7's false alarms from 12 to 4. The leftover unsure replacement invoices are what the review queue (day 6) should surface next to each overdue warning.
- **One early failure was missed because of the matching labels.** It's the playground on seed 7, which the detector catches with perfect labels. Its failing repairs are the "mulch top-up" invoices that Claude called routine grounds upkeep (see day 4).

**Threshold trade-off** (pooled held-out seeds 11–13, 15 early failures). The default of 6 was not picked from this table.

| Threshold | Perfect labels: caught | Median delay | False failing-early warnings | Rules: caught | Median delay | False failing-early warnings |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 13/15 | 216 | 41 | 10/15 | 198 | 48 |
| 5 | 13/15 | 392 | 15 | 9/15 | 433 | 18 |
| 6 (default) | 12/15 | 453 | 4 | 8/15 | 484 | 7 |

**Caveats:**

- The planted early-failure signal is about 10–20 times the normal repair rate, so high detection with perfect labels is expected by construction.
- There are 12 in-scope events per seed, so each rate rests on very few cases.
- The 15% contingency and the 90-day grace are round numbers I chose, not fitted. The generator's normal projects run up to 12% over the plan and overruns at least 17% over, so the 15% contingency sits in a gap the generator itself creates.

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
