"""
Backtest the reserve forecast: forecast from the end of ``as_of`` using only what was known then, and
compare with the balances that followed.

Rules, fixed before the first run:

* **Inputs** use only invoices dated on or before 31 December of ``as_of``: their matches, the
  completed projects and cost ratios, and the failing-early warnings a replay to that day raises.
* **Actual balance** each year = the study's starting balance + the contribution each year (same
  mode as the forecast: flat or rising) - the *true* replacement spend (the answer key's labels). The
  same contribution and no-interest assumptions sit on both sides, so the test checks the spend
  forecast, not those assumptions, and cannot tell the two contribution modes apart.
* **Band coverage**: the share of association-years whose actual balance falls inside the 10th-90th
  percentile band (to within a dollar). A well-calibrated band covers about 80%. Years where the band
  has no width (nothing falls due, so every run agrees) are counted apart: a hit there says nothing
  about calibration. **Final-year coverage** counts one value per association, since an error in an
  early year carries into every later one.
* **Median error**: the median of |actual - forecast median|, in units of the association's yearly
  contribution.
* **Running short**: an association "ran short" if its actual balance went below zero in any forecast
  year; the forecast "called it" if at least half its runs went below zero. Two baselines: how many
  were already below zero at the end of ``as_of``, and what the plain study schedule (every planned
  replacement on time at plan cost) calls.

All numbers are on synthetic data, and the forecast and the generator have the same author.
"""

from dataclasses import asdict
from datetime import date
from statistics import median

from app.domain.forecast import (
    ForecastSettings,
    completed_projects,
    contribution,
    cost_ratios,
    forecast_association,
)
from app.domain.matching import match_invoices
from app.domain.warnings import Spend, spend_from_matches, watch_spend
from app.evals.warnings import truth_matches


def backtest_seed(
    seed: int,
    labels: str = "rules",
    as_of: int = 2020,
    years: int = 5,
    n_associations: int = 20,
    contributions: str = "flat",
) -> dict:
    from app.synth.generator import generate

    ds, key = generate(seed, n_associations)
    truths = {k: asdict(v) for k, v in key.truths.items()}
    first = min(i.invoice_date.year for i in ds.invoices)
    cutoff = date(as_of, 12, 31)
    known = [i for i in ds.invoices if i.invoice_date <= cutoff]
    if labels == "rules":
        matches = match_invoices(known, ds.components, ds.associations)
    elif labels == "truth":
        ids = {i.id for i in known}
        matches = [m for m in truth_matches(truths) if m.invoice_id in ids]
    else:
        raise ValueError(f"unknown labels {labels!r}")
    spend = spend_from_matches(matches, known)
    done = completed_projects(ds.components, ds.associations, spend)
    ratios = cost_ratios(done)
    failing = {
        w.component_id
        for w in watch_spend(ds.components, ds.associations, spend, date(first, 1, 1), cutoff)
        if w.kind == "failing_early"
    }
    settings = ForecastSettings(years=years, contributions=contributions)

    true_spend = [
        Spend(i.id, truths[i.id]["component_id"], i.invoice_date, i.amount, "replacement")
        for i in ds.invoices
        if truths[i.id]["work_type"] == "replacement"
    ]
    inside = total = flat = flat_inside = final_inside = 0
    errors, called, ran_short, plain_called, already = [], set(), set(), set(), set()
    plain = ForecastSettings(years=years, adjust=False, contributions=contributions)
    rows = []
    for a in ds.associations:
        f = forecast_association(a, ds.components, spend, done, ratios, failing, first, as_of, settings)
        comps = {c.id for c in ds.components if c.association_id == a.id}
        bal = a.reserve_balance_start
        actual = {}
        for y in range(first, as_of + years + 1):
            bal += contribution(a, y, contributions) - sum(
                x.amount for x in true_spend if x.component_id in comps and x.on.year == y
            )
            actual[y] = bal
        for row in f.years:
            v = actual[row["year"]]
            hit = row["p10"] - 1 <= v <= row["p90"] + 1
            if row["p90"] - row["p10"] < 1:
                flat += 1
                flat_inside += hit
            else:
                total += 1
                inside += hit
            errors.append(abs(v - row["p50"]) / a.annual_contribution)
        last = f.years[-1]
        final_inside += last["p10"] - 1 <= actual[last["year"]] <= last["p90"] + 1
        if f.share_short >= 0.5:
            called.add(a.id)
        if actual[as_of] < 0:
            already.add(a.id)
        base = forecast_association(a, ds.components, spend, done, ratios, failing, first, as_of, plain)
        if base.share_short >= 0.5:
            plain_called.add(a.id)
        if any(actual[y] < 0 for y in range(as_of + 1, as_of + years + 1)):
            ran_short.add(a.id)
        rows.append({"association": a.id, "share_short": f.share_short, "ran_short": a.id in ran_short})
    return {
        "seed": seed,
        "labels": labels,
        "contributions": contributions,
        "as_of": as_of,
        "years": years,
        "band_coverage": round(inside / total, 3) if total else None,
        "band_years": total,
        "zero_width_years": flat,
        "zero_width_hits": flat_inside,
        "final_year_coverage": round(final_inside / len(ds.associations), 3),
        "already_below_zero": len(already),
        "plain_schedule_called_and_ran_short": len(plain_called & ran_short),
        "plain_schedule_false_calls": len(plain_called - ran_short),
        "median_error_in_contributions": round(median(errors), 2),
        "ran_short": len(ran_short),
        "called_short": len(called),
        "called_and_ran_short": len(called & ran_short),
        "missed": sorted(ran_short - called),
        "false_calls": sorted(called - ran_short),
        "cost_ratios_used": len(ratios),
        "per_association": rows,
    }
