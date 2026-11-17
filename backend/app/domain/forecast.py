"""
Reserve balance forecast: which associations run short of reserve money first.

Pure functions over plain values; nothing here reads a database or the synthetic generator.

**History.** From the study's starting balance, add the study's recommended yearly contribution and
subtract the replacement spend found in the invoices, year by year. There are no bank statements, so
two assumptions are stated wherever the forecast is shown: contributions were paid in full, and the
reserve earns no interest.

**Forecast.** A seeded Monte Carlo over the years after ``as_of``. Each run replays the study's
replacement schedule with three adjustments learned from the history:

* A part whose last completed replacement was found restarts its cycle from that year. A part past
  its planned year with no completed replacement is due in the first forecast year.
* A part with a failing-early warning (open or confirmed) is due in a random year among the next
  ``early_years``, unless the schedule already has it sooner.
* Each replacement costs the plan's inflated cost times a ratio drawn from the portfolio's own
  completed projects (actual over plan). Ratios outside ``ratio_bounds`` are treated as matching
  errors and left out; with none left, the ratio is 1.

**Contributions** follow one of two modes, applied the same way to the history and the forecast:
``flat`` (the study's recommended figure every year, the default) or ``rising`` (that figure grown
at the study's own inflation rate from the study year). The study states one figure and an inflation
rate for costs, not whether contributions rise, so both are shown and neither is fitted.

The output per year is the 10th, 50th and 90th percentile balance, the share of runs below zero, and
the first year the median goes below zero.
"""

import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.domain.matching import AssociationLike, inflated_cost
from app.domain.warnings import Spend, WatchedComponent


class FundedAssociation(AssociationLike, Protocol):
    reserve_balance_start: float
    annual_contribution: float


@dataclass(frozen=True)
class ForecastSettings:
    years: int = 10
    runs: int = 500
    seed: int = 0
    early_years: int = 3  # a failing part comes due within this many years
    ratio_bounds: tuple[float, float] = (0.5, 2.0)
    completed_share: float = 0.5  # as in the warnings: a project is done once it costs half the plan
    project_gap_days: int = 180
    # False gives the plain study schedule: every planned replacement happens on time at plan cost
    # (no history, no warnings, ratio 1). Used as the baseline in the backtest.
    adjust: bool = True
    contributions: str = "flat"  # flat | rising (at the study's inflation rate)


@dataclass(frozen=True)
class Completed:
    component_id: str
    finished_on: date
    total: float
    plan_cost: float

    @property
    def ratio(self) -> float:
        return self.total / self.plan_cost if self.plan_cost else 1.0


@dataclass
class Forecast:
    association_id: str
    as_of: int
    start_balance: float
    history: list[dict] = field(default_factory=list)  # year, contributions, reserve_spend, balance
    years: list[dict] = field(default_factory=list)  # year, p10, p50, p90, share_below_zero
    share_short: float = 0.0  # runs that go below zero in any forecast year
    first_short_year: int | None = None  # first year the median balance is below zero
    due: dict[str, int] = field(default_factory=dict)  # part -> first forecast year it is due


def contribution(assoc: FundedAssociation, year: int, mode: str) -> float:
    """The yearly contribution under ``mode``: flat, or rising at the study's inflation rate."""
    if mode == "flat":
        return assoc.annual_contribution
    if mode == "rising":
        return assoc.annual_contribution * (1 + assoc.inflation_rate) ** (year - assoc.study_year)
    raise ValueError(f"unknown contribution mode {mode!r}")


def completed_projects(
    components: Sequence[WatchedComponent],
    associations: Sequence[AssociationLike],
    spend: Iterable[Spend],
    settings: ForecastSettings | None = None,
) -> list[Completed]:
    """Replacement spend grouped into projects (gaps under ``project_gap_days``) that reached half the plan."""
    s = settings or ForecastSettings()
    comps = {c.id: c for c in components}
    assocs = {a.id: a for a in associations}
    by_comp: dict[str, list[Spend]] = defaultdict(list)
    for x in spend:
        if x.work_type == "replacement" and x.component_id in comps:
            by_comp[x.component_id].append(x)
    out = []
    for cid, xs in sorted(by_comp.items()):
        c = comps[cid]
        group: list[Spend] = []
        for x in sorted(xs, key=lambda x: (x.on, x.invoice_id)) + [None]:
            if group and (x is None or (x.on - group[-1].on).days > s.project_gap_days):
                plan = inflated_cost(c, assocs[c.association_id], group[0].on.year)
                running, crossed = 0.0, None
                for g in group:  # done on the invoice that crosses half the plan, as the warnings count it
                    running += g.amount
                    if crossed is None and running >= s.completed_share * plan:
                        crossed = g.on
                if crossed is not None:
                    out.append(Completed(cid, crossed, round(running, 2), round(plan, 2)))
                group = []
            if x is not None:
                group.append(x)
    return out


def cost_ratios(done: Iterable[Completed], settings: ForecastSettings | None = None) -> list[float]:
    s = settings or ForecastSettings()
    lo, hi = s.ratio_bounds
    return sorted(round(d.ratio, 4) for d in done if lo <= d.ratio <= hi)


def first_due(c: WatchedComponent, done: Sequence[Completed], as_of: int) -> int:
    """First year after ``as_of`` the part is due, from its last completed replacement or the study."""
    last = max((d.finished_on.year for d in done if d.component_id == c.id), default=None)
    due = last + c.useful_life_years if last is not None else c.planned_year
    return max(due, as_of + 1)  # past due and never replaced: due now


def forecast_association(
    assoc: FundedAssociation,
    components: Sequence[WatchedComponent],
    spend: Iterable[Spend],
    done: Sequence[Completed],
    ratios: Sequence[float],
    failing: Iterable[str],
    first_year: int,
    as_of: int,
    settings: ForecastSettings | None = None,
) -> Forecast:
    s = settings or ForecastSettings()
    comps = [c for c in components if c.association_id == assoc.id]
    ids = {c.id for c in comps}
    reserve: dict[int, float] = defaultdict(float)
    for x in spend:
        if x.work_type == "replacement" and x.component_id in ids and x.on.year <= as_of:
            reserve[x.on.year] += x.amount

    out = Forecast(assoc.id, as_of, 0.0)
    balance = assoc.reserve_balance_start
    for y in range(first_year, as_of + 1):
        paid = contribution(assoc, y, s.contributions)
        balance += paid - reserve[y]
        out.history.append(
            {
                "year": y,
                "contributions": round(paid, 2),
                "reserve_spend": round(reserve[y], 2),
                "balance": round(balance, 2),
            }
        )
    out.start_balance = round(balance, 2)

    if s.adjust:
        due = {c.id: first_due(c, [d for d in done if d.component_id == c.id], as_of) for c in comps}
        failing = set(failing) & ids
        pool = list(ratios) or [1.0]
    else:
        due = {c.id: _next_planned(c, as_of) for c in comps}
        failing, pool = set(), [1.0]
    out.due = dict(sorted(due.items()))
    rng = random.Random(f"{s.seed}:{assoc.id}")
    horizon = range(as_of + 1, as_of + s.years + 1)
    paths: list[list[float]] = []
    for _ in range(s.runs):
        first = dict(due)
        for cid in failing:
            first[cid] = min(first[cid], as_of + rng.randint(1, s.early_years))
        spend_by_year: dict[int, float] = defaultdict(float)
        for c in comps:
            y = first[c.id]
            while y <= horizon[-1]:
                spend_by_year[y] += inflated_cost(c, assoc, y) * rng.choice(pool)
                y += c.useful_life_years
        bal, path = balance, []
        for y in horizon:
            bal += contribution(assoc, y, s.contributions) - spend_by_year[y]
            path.append(bal)
        paths.append(path)

    for i, y in enumerate(horizon):
        col = sorted(p[i] for p in paths)
        row = {
            "year": y,
            "p10": round(_q(col, 0.1), 2),
            "p50": round(_q(col, 0.5), 2),
            "p90": round(_q(col, 0.9), 2),
            "share_below_zero": round(sum(v < 0 for v in col) / len(col), 3),
        }
        out.years.append(row)
        if out.first_short_year is None and row["p50"] < 0:
            out.first_short_year = y
    out.share_short = round(sum(any(v < 0 for v in p) for p in paths) / len(paths), 3)
    return out


def _next_planned(c: WatchedComponent, as_of: int) -> int:
    """The study's own next cycle year after ``as_of``, assuming every earlier one happened on time."""
    y = c.planned_year
    while y <= as_of:
        y += c.useful_life_years
    return y


def _q(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an already sorted list."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)
