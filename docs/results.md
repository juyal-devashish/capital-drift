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
