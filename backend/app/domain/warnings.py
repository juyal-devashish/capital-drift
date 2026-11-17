"""
Repair-or-replace warnings: watch each reserve component's matched spend against its plan over time.

Three checks, each written as a call a board or manager can act on:

* **failing_early**: repairs are coming much faster than usual for a part this age, while the plan
  still has its replacement more than a year out. A Poisson CUSUM on monthly repair *counts*
  (not dollars: one big partial repair shouldn't look like a failing part). The usual rate is
  learned from the portfolio itself, pooled by age as a share of useful life, using only months
  already seen.
* **overdue**: the plan's replacement year has passed (plus a grace period for final invoices) and
  no completed replacement has been found.
* **over_budget**: a replacement project has cost more than the plan's inflated cost plus a
  contingency.

Every warning uses only spend dated on or before the day it fires, so replaying a history gives the
same warnings a live system would have raised. Nothing here knows how the synthetic data was made.
"""

import math
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from app.domain.matching import AssociationLike, MatchResult, inflated_cost

KINDS = ("failing_early", "overdue", "over_budget")


class WatchedComponent(Protocol):
    id: str
    association_id: str
    name: str
    location: str | None
    useful_life_years: int
    remaining_life_years: int
    replacement_cost: float
    planned_year: int


class InvoiceDated(Protocol):
    id: str
    invoice_date: date
    amount: float


@dataclass(frozen=True)
class Spend:
    """One invoice's money on one component, as a matcher labelled it."""

    invoice_id: str
    component_id: str
    on: date
    amount: float
    work_type: str  # repair | replacement


@dataclass
class SpendWarning:
    kind: str  # failing_early | overdue | over_budget
    association_id: str
    component_id: str
    fired_on: date
    headline: str
    message: str
    numbers: dict = field(default_factory=dict)
    invoice_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WatchSettings:
    # failing_early: Poisson CUSUM tuned to catch repairs arriving at `rate_ratio` x the usual rate.
    rate_ratio: float = 4.0
    # Chosen before scoring any planted event: at a usual 0.5 repairs a year, a healthy part runs
    # about 600 years before a false alarm (`in_control_years`), so a 20-association portfolio
    # (~2,500 watched component-years) should see about 4 if the baseline were exact.
    cusum_threshold: float = 6.0
    burn_in_months: int = 12  # learn the usual rate before watching
    prior_months: float = 120.0  # weight of the portfolio-wide rate when a bucket has little data
    age_bucket: float = 0.25  # share of useful life per bucket; last bucket is open-ended
    n_buckets: int = 6
    min_rate: float = 0.002  # repairs per component-month, a floor so the CUSUM never divides by ~0
    due_soon_years: int = 1  # no failing_early warning when the plan replaces it this year or next
    # replacements
    project_gap_days: int = 180  # replacement invoices closer than this belong to one project
    completed_share: float = 0.5  # a project counts as done once it has cost this share of the plan
    over_budget_ratio: float = 1.15  # beyond a 15% contingency on the plan's inflated cost
    overdue_grace_days: int = 90  # after the end of the due year, for final invoices to arrive


def spend_from_matches(matches: Iterable[MatchResult], invoices: Iterable[InvoiceDated]) -> list[Spend]:
    """Repairs and replacements with a component; routine and unsure are not component spend."""
    by_id = {i.id: i for i in invoices}
    out = []
    for m in matches:
        if m.label in ("repair", "replacement") and m.component_id:
            inv = by_id[m.invoice_id]
            out.append(Spend(m.invoice_id, m.component_id, inv.invoice_date, inv.amount, m.label))
    return out


def watch_window(invoices: Iterable[InvoiceDated]) -> tuple[date, date]:
    """1 January of the first invoice's year through 31 December of the last invoice's year."""
    days = [i.invoice_date for i in invoices]
    return date(min(days).year, 1, 1), date(max(days).year, 12, 31)


def _month_end(year: int, month: int) -> date:
    first_next = date(year + month // 12, month % 12 + 1, 1)
    return first_next - timedelta(days=1)


def _months(start: date, through: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (through.year, through.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _where(c: WatchedComponent) -> str:
    return f"{c.name} ({c.location})" if c.location else c.name


def _the(c: WatchedComponent) -> str:
    """The part's name mid-sentence: "the vinyl siding (Bldg B)" (acronyms like HVAC keep their case)."""
    name = _where(c)
    if len(name) > 1 and name[1].islower():
        name = name[0].lower() + name[1:]
    return f"the {name}"


def _jobs(n: int) -> str:
    return f"{n} repair job{'' if n == 1 else 's'}"


@dataclass
class _Project:
    start: date
    last: date
    plan_cost: float
    total: float = 0.0
    invoice_ids: list[str] = field(default_factory=list)
    completed: bool = False
    over_fired: bool = False


@dataclass
class _State:
    comp: WatchedComponent
    assoc: AssociationLike
    due_year: int
    replaced_on: date | None = None
    cusum: float = 0.0
    climb_from: date | None = None  # first day of the month the CUSUM last rose from zero
    rising_fired: bool = False
    overdue_fired: bool = False
    project: _Project | None = None
    repairs: list[Spend] = field(default_factory=list)  # since the last completed replacement

    def age_share(self, on: date, study_year: int) -> float:
        c = self.comp
        if self.replaced_on is not None:
            age = (on - self.replaced_on).days / 365.25
        else:
            age = (c.useful_life_years - c.remaining_life_years) + (on.year - study_year) + (on.month - 1) / 12
        return max(age, 0.0) / c.useful_life_years


class _Baseline:
    """Repairs per component-month, pooled across the portfolio by age bucket, from months seen so far."""

    def __init__(self, s: WatchSettings):
        self.s = s
        self.repairs = [0.0] * s.n_buckets
        self.months = [0.0] * s.n_buckets

    def bucket(self, age_share: float) -> int:
        return min(int(age_share / self.s.age_bucket), self.s.n_buckets - 1)

    def rate(self, b: int) -> float:
        total_m = sum(self.months)
        overall = sum(self.repairs) / total_m if total_m else self.s.min_rate
        r = (self.repairs[b] + self.s.prior_months * overall) / (self.months[b] + self.s.prior_months)
        return max(r, self.s.min_rate)

    def add(self, b: int, n: int) -> None:
        self.repairs[b] += n
        self.months[b] += 1


def watch_spend(
    components: Sequence[WatchedComponent],
    associations: Sequence[AssociationLike],
    spend: Iterable[Spend],
    start: date,
    through: date,
    settings: WatchSettings | None = None,
) -> list[SpendWarning]:
    """Replay spend month by month from ``start`` to ``through`` and return warnings in firing order."""
    s = settings or WatchSettings()
    assocs = {a.id: a for a in associations}
    states = {c.id: _State(c, assocs[c.association_id], c.planned_year) for c in sorted(components, key=lambda c: c.id)}
    by_month: dict[tuple[int, int], list[Spend]] = defaultdict(list)
    for x in sorted(spend, key=lambda x: (x.on, x.invoice_id)):
        if x.component_id in states and start <= x.on <= through:
            by_month[(x.on.year, x.on.month)].append(x)

    baseline = _Baseline(s)
    warnings: list[SpendWarning] = []
    log_r = math.log(s.rate_ratio)

    for i, (y, m) in enumerate(_months(start, through)):
        end = min(_month_end(y, m), through)
        counts: dict[str, int] = defaultdict(int)
        for x in by_month.get((y, m), []):
            st = states[x.component_id]
            if x.work_type == "replacement":
                warnings.extend(_add_replacement(st, x, s))
            else:
                st.repairs.append(x)
                counts[x.component_id] += 1

        rated = []
        for cid, st in states.items():
            b = baseline.bucket(st.age_share(end, st.assoc.study_year))
            rated.append((st, b, counts.get(cid, 0)))
        if i >= s.burn_in_months:
            for st, b, n in rated:
                lam = baseline.rate(b)
                before = st.cusum
                st.cusum = max(0.0, st.cusum + n * log_r - (s.rate_ratio - 1) * lam)
                if before == 0.0 and st.cusum > 0.0:
                    st.climb_from = date(y, m, 1)
                if st.cusum >= s.cusum_threshold and not st.rising_fired and st.due_year > y + s.due_soon_years:
                    st.rising_fired = True
                    warnings.append(_failing_early(st, end, lam))
        for _st, b, n in rated:
            baseline.add(b, n)

        for st in states.values():
            overdue_from = date(st.due_year, 12, 31) + timedelta(days=s.overdue_grace_days)
            in_progress = (
                st.project is not None
                and not st.project.completed
                and (end - st.project.last).days <= (s.project_gap_days)
            )
            if not st.overdue_fired and end >= overdue_from and not in_progress:
                st.overdue_fired = True
                warnings.append(_overdue(st, end))
    return warnings


def _add_replacement(st: _State, x: Spend, s: WatchSettings) -> list[SpendWarning]:
    p = st.project
    if p is None or (x.on - p.last).days > s.project_gap_days:
        p = st.project = _Project(x.on, x.on, inflated_cost(st.comp, st.assoc, x.on.year))
    p.total += x.amount
    p.last = x.on
    p.invoice_ids.append(x.invoice_id)
    out = []
    if not p.over_fired and p.total > s.over_budget_ratio * p.plan_cost:
        p.over_fired = True
        out.append(_over_budget(st, p, x.on))
    if not p.completed and p.total >= s.completed_share * p.plan_cost:
        p.completed = True
        st.replaced_on = x.on
        st.due_year = x.on.year + st.comp.useful_life_years
        st.cusum, st.climb_from, st.rising_fired, st.overdue_fired = 0.0, None, False, False
        st.repairs = []
    return out


def _failing_early(st: _State, on: date, lam_month: float) -> SpendWarning:
    c = st.comp
    since = st.climb_from or on
    climb = [r for r in st.repairs if r.on >= since]
    recent = [r for r in st.repairs if (on - r.on).days < 365]
    amt12 = sum(r.amount for r in recent)
    months = (on.year - since.year) * 12 + on.month - since.month + 1
    usual = lam_month * 12
    plan_cost = inflated_cost(c, st.assoc, st.due_year)
    per_year = plan_cost / c.useful_life_years
    lines = [
        f"{_jobs(len(climb)).capitalize()} on {_the(c)} in {months} months since {since:%b %Y}, "
        f"costing {_money(sum(r.amount for r in climb))}. Parts this age usually need about {usual:.1f} a year.",
        f"The plan replaces it in {st.due_year} for about {_money(plan_cost)}.",
    ]
    if amt12 > per_year:
        lines.append(
            f"Repairs in the last 12 months ({_money(amt12)}) cost more than a new one costs per year of its "
            f"life ({_money(per_year)}). Consider moving the replacement up."
        )
    else:
        lines.append("If repairs keep this pace, price repairing against replacing it early.")
    return SpendWarning(
        "failing_early",
        c.association_id,
        c.id,
        on,
        f"{_where(c)}: failing early",
        " ".join(lines),
        {
            "climb_from": since.isoformat(),
            "repairs_since_climb": len(climb),
            "repair_spend_since_climb": round(sum(r.amount for r in climb), 2),
            "repair_spend_12m": round(amt12, 2),
            "usual_repairs_per_year": round(usual, 2),
            "planned_year": st.due_year,
            "plan_cost": round(plan_cost, 2),
            "plan_cost_per_year": round(per_year, 2),
            "cusum": round(st.cusum, 3),
        },
        [r.invoice_id for r in climb],
    )


def _overdue(st: _State, on: date) -> SpendWarning:
    c = st.comp
    since = [r for r in st.repairs if r.on.year > st.due_year]
    amt = sum(r.amount for r in since)
    repairs = f"Repairs since then: {_jobs(len(since))}, {_money(amt)}." if since else "No repairs since then."
    message = (
        f"The plan put replacement of {_the(c)} in {st.due_year}, and no replacement spend has been "
        f"found by {on:%b %-d, %Y}. {repairs} "
        "Schedule the replacement, or update the study with a new date and the part's condition."
    )
    return SpendWarning(
        "overdue",
        c.association_id,
        c.id,
        on,
        f"{_where(c)}: past its {st.due_year} replacement",
        message,
        {"planned_year": st.due_year, "repairs_since_due": len(since), "repair_spend_since_due": round(amt, 2)},
        [r.invoice_id for r in since],
    )


def _over_budget(st: _State, p: _Project, on: date) -> SpendWarning:
    c = st.comp
    over = p.total / p.plan_cost - 1
    message = (
        f"Replacing {_the(c)} has cost {_money(p.total)} so far, {over:.0%} over the plan's "
        f"{_money(p.plan_cost)} in {p.start.year} dollars. Update the study's cost for the next cycle "
        "and check that reserve contributions still cover it."
    )
    return SpendWarning(
        "over_budget",
        c.association_id,
        c.id,
        on,
        f"{_where(c)}: replacement {over:.0%} over plan",
        message,
        {"project_total": round(p.total, 2), "plan_cost": round(p.plan_cost, 2), "over_share": round(over, 4)},
        list(p.invoice_ids),
    )


def in_control_years(
    rate_per_year: float, settings: WatchSettings | None = None, runs: int = 2000, seed: int = 0
) -> float:
    """Mean years until the CUSUM falsely fires on a part repaired at its usual rate (simulated).

    Used to pick ``cusum_threshold`` from a target false-alarm rate rather than from the planted events.
    """
    s = settings or WatchSettings()
    rng = random.Random(seed)
    lam = rate_per_year / 12
    log_r, drift = math.log(s.rate_ratio), (s.rate_ratio - 1) * lam
    cap, total = 12_000, 0  # 1,000 years
    for _ in range(runs):
        cusum, month = 0.0, 0
        while month < cap:
            month += 1
            n, p, limit = 0, rng.random(), math.exp(-lam)
            while p > limit:  # Poisson draw by multiplication
                n += 1
                p *= rng.random()
            cusum = max(0.0, cusum + n * log_r - drift)
            if cusum >= s.cusum_threshold:
                break
        total += month
    return total / runs / 12
