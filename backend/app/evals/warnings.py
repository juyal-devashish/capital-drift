"""
Score repair-or-replace warnings against a synthetic answer key.

Scoring rules, fixed before looking at any results:

* Each planted event expects one warning kind on its component: an **early failure** expects
  ``failing_early``, a **deferred** replacement expects ``overdue``, a **cost overrun** expects
  ``over_budget``. **Miscoded** events are out of scope here: they are replacements booked to the
  operating fund, which the wrong-fund flags from matching already catch.
* An event is **detected** when a warning of its kind on its component fires on or after the event's
  onset. The earliest such warning is credited; its **delay** is ``fired_on - onset`` in days.
  Onset means: the first failing repairs (early failure); 31 December of the planned year (deferred);
  1 January of the planned year (cost overrun, so its delay includes waiting for the project).
* For early failures, the **lead** is how many days the warning came before the emergency
  replacement (the event's replacement invoices in the answer key). Negative means it came after.
  None means the part was still failing when the history ends.
* Every warning not credited to an event is a **false alarm**, including warnings on an event's
  component of another kind or before its onset. The rate is per 100 watched component-years.

All numbers are on synthetic data, and the detector and the generator have the same author.
"""

from collections import Counter
from collections.abc import Sequence
from datetime import date
from statistics import median

from app.domain.matching import MatchResult
from app.domain.warnings import SpendWarning

EXPECTED_KIND = {"early_failure": "failing_early", "deferred": "overdue", "cost_overrun": "over_budget"}


def truth_matches(truths: dict[str, dict]) -> list[MatchResult]:
    """The answer key's labels as if a perfect matcher had produced them (detector-only baseline)."""
    out = []
    for inv_id, t in truths.items():
        label = t["work_type"]
        out.append(MatchResult(inv_id, label, t.get("component_id"), 1.0, ["answer key"], [], "truth"))
    return out


def score_warnings(
    warnings: Sequence[SpendWarning],
    events: Sequence[dict],
    truths: dict[str, dict],
    invoice_dates: dict[str, date],
    component_years: float,
) -> dict:
    credited: set[int] = set()
    per_event = []
    for e in events:
        kind = EXPECTED_KIND.get(e["type"])
        if kind is None:
            continue
        onset = date.fromisoformat(e["onset"]) if isinstance(e["onset"], str) else e["onset"]
        hits = [
            (w.fired_on, i)
            for i, w in enumerate(warnings)
            if w.kind == kind and w.component_id == e["component_id"] and w.fired_on >= onset and i not in credited
        ]
        row = {"event": e["id"], "type": e["type"], "component_id": e["component_id"], "onset": onset.isoformat()}
        if hits:
            fired_on, i = min(hits)
            credited.add(i)
            row.update(detected=True, fired_on=fired_on.isoformat(), delay_days=(fired_on - onset).days)
        else:
            row.update(detected=False, fired_on=None, delay_days=None)
        if e["type"] == "early_failure":
            replaced = [
                invoice_dates[k]
                for k, t in truths.items()
                if t.get("event_id") == e["id"] and t["work_type"] == "replacement"
            ]
            row["replaced_on"] = min(replaced).isoformat() if replaced else None
            row["lead_days"] = (min(replaced) - fired_on).days if (hits and replaced) else None
        per_event.append(row)

    false = [w for i, w in enumerate(warnings) if i not in credited]
    by_type = {}
    for etype in EXPECTED_KIND:
        rows = [r for r in per_event if r["type"] == etype]
        delays = [r["delay_days"] for r in rows if r["detected"]]
        entry = {
            "planted": len(rows),
            "detected": len(delays),
            "median_delay_days": median(delays) if delays else None,
        }
        if etype == "early_failure":
            leads = [r["lead_days"] for r in rows if r.get("lead_days") is not None]
            entry["warned_before_replacement"] = sum(x > 0 for x in leads)
            entry["replaced_in_history"] = sum(r["replaced_on"] is not None for r in rows)
        by_type[etype] = entry
    return {
        "warnings": len(warnings),
        "by_kind": dict(sorted(Counter(w.kind for w in warnings).items())),
        "events": by_type,
        "detected": sum(r["detected"] for r in per_event),
        "planted": len(per_event),
        "false_alarms": len(false),
        "false_alarms_by_kind": dict(sorted(Counter(w.kind for w in false).items())),
        "false_alarms_per_100_component_years": round(100 * len(false) / component_years, 2)
        if component_years
        else None,
        "per_event": per_event,
        "false_alarm_list": [
            {"kind": w.kind, "component_id": w.component_id, "fired_on": w.fired_on.isoformat(), "headline": w.headline}
            for w in false
        ],
    }


def evaluate_seed(seed: int, labels: str = "rules", n_associations: int = 20, settings=None) -> dict:
    """Generate a portfolio in memory, label its spend, watch it and score the warnings.

    ``labels`` is ``rules`` (the rule matcher, free to run) or ``truth`` (the answer key's own labels,
    which shows what the detector does with perfect matching). Touches no database.
    """
    from dataclasses import asdict

    from app.domain.matching import match_invoices
    from app.domain.warnings import spend_from_matches, watch_spend, watch_window
    from app.synth.generator import generate

    ds, key = generate(seed, n_associations)
    truths = {k: asdict(v) for k, v in key.truths.items()}
    if labels == "truth":
        matches = truth_matches(truths)
    elif labels == "rules":
        matches = match_invoices(ds.invoices, ds.components, ds.associations)
    else:
        raise ValueError(f"unknown labels {labels!r}")
    start, through = watch_window(ds.invoices)
    warnings = watch_spend(
        ds.components, ds.associations, spend_from_matches(matches, ds.invoices), start, through, settings
    )
    events = [{**asdict(e), "onset": e.onset.isoformat()} for e in key.events]
    report = score_warnings(
        warnings,
        events,
        truths,
        {i.id: i.invoice_date for i in ds.invoices},
        component_years(len(ds.components), start, through, settings),
    )
    return {"seed": seed, "labels": labels, **report}


def component_years(n_components: int, start: date, through: date, settings=None) -> float:
    """Component-years the failing-early check actually watches (after its burn-in)."""
    from app.domain.warnings import WatchSettings

    s = settings or WatchSettings()
    months = (through.year - start.year) * 12 + through.month - start.month + 1
    return n_components * max(months - s.burn_in_months, 0) / 12
