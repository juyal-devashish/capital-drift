"""
What the board and manager screens show: each association's status in plain words, and its plan
against actual spend year by year. Pure functions over plain values; nothing here reads a database.

**Status rule** (stated on the board screen too):

* **Red**: at least one *failing early* or *overdue* warning that is open (not yet checked by a
  property manager) or confirmed.
* **Amber**: no red warning, but an open or confirmed *over budget* warning, or invoices nobody has
  placed yet worth at least 10% of the association's yearly reserve contribution.
* **Green**: none of those. Dismissed warnings and warnings a rerun no longer raises don't count.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.domain.matching import AssociationLike, MatchResult, inflated_cost
from app.domain.warnings import InvoiceDated, WatchedComponent

COUNTED = ("open", "confirmed")
RED_KINDS = ("failing_early", "overdue")
UNPLACED_SHARE = 0.10
STATUS_RULE = (
    "Red: a part failing early or past its planned replacement, either not yet checked or confirmed by a "
    "property manager. Amber: a replacement over budget, or invoices not yet placed worth at least 10% of "
    "the yearly reserve contribution. Green: none of those. Dismissed warnings don't count."
)


@dataclass(frozen=True)
class QueueEntry:
    """The parts of a review item the board needs."""

    kind: str  # warning | invoice
    warning_kind: str | None
    status: str
    title: str
    amount_at_stake: float
    checked_by: str | None = None  # who confirmed it, if anyone


@dataclass
class AssociationStatus:
    status: str  # red | amber | green
    reasons: list[str] = field(default_factory=list)
    open_warnings: int = 0
    confirmed_warnings: int = 0
    unplaced_invoices: int = 0
    unplaced_amount: float = 0.0


def association_status(entries: Iterable[QueueEntry], annual_contribution: float) -> AssociationStatus:
    entries = list(entries)
    warnings = [e for e in entries if e.kind == "warning" and e.status in COUNTED]
    unplaced = [e for e in entries if e.kind == "invoice" and e.status == "open"]
    unplaced_amount = sum(e.amount_at_stake for e in unplaced)

    def line(e: QueueEntry) -> str:
        checked = f"confirmed by {e.checked_by}" if e.status == "confirmed" else "not yet checked by the manager"
        return f"{e.title} ({checked})"

    red = [e for e in warnings if e.warning_kind in RED_KINDS]
    amber = [e for e in warnings if e.warning_kind not in RED_KINDS]
    reasons = [line(e) for e in sorted(red, key=_order) + sorted(amber, key=_order)]
    many_unplaced = unplaced_amount >= UNPLACED_SHARE * annual_contribution and unplaced_amount > 0
    if unplaced:
        reasons.append(
            f"{len(unplaced)} invoice{'s' if len(unplaced) != 1 else ''} worth ${unplaced_amount:,.0f} "
            "not yet placed against a part of the plan"
        )
    status = "red" if red else "amber" if (amber or many_unplaced) else "green"
    return AssociationStatus(
        status,
        reasons,
        open_warnings=sum(e.status == "open" for e in warnings),
        confirmed_warnings=sum(e.status == "confirmed" for e in warnings),
        unplaced_invoices=len(unplaced),
        unplaced_amount=round(unplaced_amount, 2),
    )


def _order(e: QueueEntry) -> tuple:
    return (e.status != "confirmed", -e.amount_at_stake, e.title)


def plan_schedule(
    component: WatchedComponent, assoc: AssociationLike, first: int, last: int
) -> list[tuple[int, float]]:
    """The study's replacement cycles inside [first, last]: the planned year, then every useful life after."""
    out, year = [], component.planned_year
    while year <= last:
        if year >= first:
            out.append((year, round(inflated_cost(component, assoc, year), 2)))
        year += component.useful_life_years
    return out


def year_by_year(
    components: Sequence[WatchedComponent],
    assoc: AssociationLike,
    invoices: Iterable[InvoiceDated],
    matches: Iterable[MatchResult],
    first: int,
    last: int,
) -> dict:
    """Plan against actual for one association: totals per year, and per part the planned and found years."""
    comps = {c.id: c for c in components if c.association_id == assoc.id}
    label = {m.invoice_id: m for m in matches}
    years = {
        y: {"year": y, "planned": 0.0, "replacements": 0.0, "repairs": 0.0, "routine": 0.0, "unplaced": 0.0}
        for y in range(first, last + 1)
    }
    planned_by_part: dict[str, list[int]] = defaultdict(list)
    for c in comps.values():
        for y, cost in plan_schedule(c, assoc, first, last):
            years[y]["planned"] += cost
            planned_by_part[c.id].append(y)

    found: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    repairs: dict[str, float] = defaultdict(float)
    for inv in invoices:
        if inv.association_id != assoc.id or inv.invoice_date.year not in years:
            continue
        m = label.get(inv.id)
        row = years[inv.invoice_date.year]
        if m is None or m.label == "unsure":
            row["unplaced"] += inv.amount
        elif m.label == "routine":
            row["routine"] += inv.amount
        elif m.label == "replacement" and m.component_id in comps:
            row["replacements"] += inv.amount
            found[m.component_id][inv.invoice_date.year] += inv.amount
        elif m.component_id in comps:
            row["repairs"] += inv.amount
            repairs[m.component_id] += inv.amount

    parts = [
        {
            "component_id": c.id,
            "name": c.name,
            "location": c.location,
            "useful_life_years": c.useful_life_years,
            "replacement_cost": c.replacement_cost,
            "planned_years": planned_by_part.get(c.id, []),
            "replacement_spend_by_year": {str(y): round(v, 2) for y, v in sorted(found[c.id].items())},
            "repair_spend": round(repairs.get(c.id, 0.0), 2),
        }
        for c in sorted(comps.values(), key=lambda c: c.id)
    ]
    rows = [{k: round(v, 2) if isinstance(v, float) else v for k, v in r.items()} for r in years.values()]
    return {"years": rows, "parts": parts}
