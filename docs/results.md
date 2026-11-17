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
