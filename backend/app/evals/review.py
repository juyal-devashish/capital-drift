"""
How much review the queue needs: a simulated property manager works only the overdue warnings.

The simulated reviewer opens each overdue warning, looks at the candidate invoices the queue lists
beside it (``overdue_candidates``), and assigns each one to its true part, or routine, from the
answer key. Code then applies the 15% rule and the warnings are rerun, as in the app. This repeats
until no overdue warning has an unchecked candidate.

It is an **upper bound**: a real reviewer can be wrong or skip invoices. Rules fixed before running:

* **Invoices reviewed** counts each candidate once, however many warnings list it.
* **False alarms** and **detections** are scored by ``score_warnings`` before and after, unchanged.
* **Detections lost** counts planted events detected before review but not after.

All numbers are on synthetic data.
"""

from collections.abc import Sequence
from dataclasses import replace

from app.domain.matching import MatchResult, fund_flag, with_work_type
from app.domain.warnings import overdue_candidates, spend_from_matches, watch_spend, watch_window
from app.evals.warnings import component_years, score_warnings


def simulate_review(components, associations, invoices, matches: Sequence[MatchResult], truths: dict, events) -> dict:
    comps = {c.id: c for c in components}
    assocs = {a.id: a for a in associations}
    invs = {i.id: i for i in invoices}
    start, through = watch_window(invoices)
    years = component_years(len(components), start, through)
    dates = {i.id: i.invoice_date for i in invoices}

    def watch(ms):
        return watch_spend(components, associations, spend_from_matches(ms, invoices), start, through)

    def score(ws):
        return score_warnings(ws, events, truths, dates, years)

    current = {m.invoice_id: m for m in matches}
    before = score(watch(list(current.values())))
    reviewed: set[str] = set()
    rounds = 0
    while True:
        warnings = watch(list(current.values()))
        todo = []
        for w in warnings:
            if w.kind == "overdue":
                todo += [
                    i
                    for i in overdue_candidates(w, components, associations, invoices, current.values())
                    if i not in reviewed
                ]
        if not todo:
            break
        rounds += 1
        for inv_id in dict.fromkeys(todo):
            reviewed.add(inv_id)
            inv, t = invs[inv_id], truths[inv_id]
            if t["component_id"] is None:
                m = MatchResult(inv_id, "routine", None, 1.0, ["simulated reviewer"])
            else:
                comp = comps[t["component_id"]]
                m = with_work_type(inv, comp, assocs[comp.association_id], 1.0, ["simulated reviewer"])
            m = replace(m, method="reviewer")
            fund_flag(m, inv)
            current[inv_id] = m
    after = score(warnings)
    lost = [
        r["event"]
        for r, a in zip(before["per_event"], after["per_event"], strict=True)
        if r["detected"] and not a["detected"]
    ]
    return {
        "invoices_reviewed": len(reviewed),
        "rounds": rounds,
        "unsure_in_queue": sum(m.label == "unsure" for m in matches),
        "before": _summary(before),
        "after": _summary(after),
        "detections_lost": lost,
    }


def _summary(r: dict) -> dict:
    return {
        "warnings": r["warnings"],
        "detected": r["detected"],
        "planted": r["planted"],
        "false_alarms": r["false_alarms"],
        "false_alarms_by_kind": r["false_alarms_by_kind"],
    }


def evaluate_review_seed(seed: int, n_associations: int = 20) -> dict:
    """In memory, rules-only matches (free). Touches no database."""
    from dataclasses import asdict

    from app.domain.matching import match_invoices
    from app.synth.generator import generate

    ds, key = generate(seed, n_associations)
    matches = match_invoices(ds.invoices, ds.components, ds.associations)
    truths = {k: asdict(v) for k, v in key.truths.items()}
    events = [{**asdict(e), "onset": e.onset.isoformat()} for e in key.events]
    return {
        "seed": seed,
        "labels": "rules",
        **simulate_review(ds.components, ds.associations, ds.invoices, matches, truths, events),
    }


def evaluate_review_db(db, answer_key: dict, method: str = "combined") -> dict:
    """On the loaded portfolio's stored matches (``combined`` = rules + Claude). Writes nothing."""
    from sqlalchemy import select

    from app.db.models import Association, Invoice, ReserveComponent
    from app.services.llm_matching import combined_matches, stored_matches

    matches = combined_matches(db) if method == "combined" else stored_matches(db, method)
    return {
        "seed": answer_key["seed"],
        "labels": method,
        **simulate_review(
            list(db.scalars(select(ReserveComponent))),
            list(db.scalars(select(Association))),
            list(db.scalars(select(Invoice))),
            matches,
            answer_key["invoices"],
            answer_key["events"],
        ),
    }
