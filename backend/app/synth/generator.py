"""
Synthetic portfolio generator: associations, reserve studies, ten years of vendor invoices and an
answer key with planted problems.

Everything is driven by one seeded ``random.Random``, so the same seed always produces the same
data. The answer key (true component and fund per invoice, planted problems) is returned
separately and must never be loaded into the app database.

The model of the world, kept deliberately simple:

* Each reserve component has a useful life and an age. Repairs arrive as a Poisson process whose
  rate grows with age (``_wear``), so an old component costs more to keep running.
* When a component reaches its planned year it is replaced (a project billed as deposit, progress
  and final invoices) and its age resets.
* Routine services (landscaping, cleaning, snow, pest, trash) are operating costs tied to no
  component.
* Planted problems bend that picture: a component failing early, a replacement over budget, a
  replacement deferred past its planned year, or reserve work booked to the operating fund.
"""

import math
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from app.synth.catalog import (
    KINDS,
    NAME_STEMS,
    PORTFOLIO_NAMES,
    ROUTINE_SERVICES,
    TOWNS,
    VENDORS,
    ComponentSpec,
    KindSpec,
)

STUDY_YEAR = 2016
FIRST_YEAR = 2016
LAST_YEAR = 2025
HISTORY_END = date(LAST_YEAR, 12, 31)

# A repair costing at least this share of the component's replacement cost is capital work under
# the usual reserve policy. Invoices just under it are the "ambiguous" cases.
CAPITAL_THRESHOLD = 0.15
PROJECT_SPLIT_THRESHOLD = 40_000  # projects above this are billed as deposit + final (+ progress)

EVENT_PLAN = {"early_failure": 5, "cost_overrun": 4, "deferred": 3, "miscoded": 3}


# ------------------------------------------------------------------------------------ data classes
@dataclass
class SynthPortfolio:
    id: str
    name: str


@dataclass
class SynthAssociation:
    id: str
    portfolio_id: str
    name: str
    kind: str
    town: str
    units: int
    buildings: int
    year_built: int
    study_year: int
    inflation_rate: float
    reserve_balance_start: float
    annual_contribution: float


@dataclass
class SynthComponent:
    id: str
    association_id: str
    category: str
    name: str
    location: str | None
    useful_life_years: int
    remaining_life_years: int
    replacement_cost: float
    planned_year: int


@dataclass
class SynthInvoice:
    id: str
    association_id: str
    vendor_name: str
    invoice_number: str
    invoice_date: date
    amount: float
    memo: str
    fund_booked: str


@dataclass
class InvoiceTruth:
    """What the invoice really was. Lives only in the answer key."""

    fund: str  # operating | reserve
    work_type: str  # routine | repair | replacement
    component_id: str | None = None
    secondary_component_id: str | None = None
    project_id: str | None = None
    event_id: str | None = None
    ambiguous: bool = False
    note: str | None = None


@dataclass
class PlantedEvent:
    id: str
    type: str  # early_failure | cost_overrun | deferred | miscoded
    association_id: str
    component_id: str
    onset: date  # when the problem starts to show in the invoices
    description: str


@dataclass
class SynthDataset:
    seed: int
    portfolios: list[SynthPortfolio]
    associations: list[SynthAssociation]
    components: list[SynthComponent]
    invoices: list[SynthInvoice]


@dataclass
class AnswerKey:
    seed: int
    truths: dict[str, InvoiceTruth]  # invoice id -> truth
    events: list[PlantedEvent]
    policy: dict = field(
        default_factory=lambda: {
            "capital_threshold_share_of_replacement_cost": CAPITAL_THRESHOLD,
            "rule": "Replacements are reserve spend. Repairs and routine services are operating spend.",
        }
    )

    def summary(self) -> dict:
        work = Counter(t.work_type for t in self.truths.values())
        return {
            "invoices": len(self.truths),
            "by_work_type": dict(sorted(work.items())),
            "ambiguous": sum(t.ambiguous for t in self.truths.values()),
            "events": dict(sorted(Counter(e.type for e in self.events).items())),
        }

    def to_json(self) -> dict:
        return {
            "label": "SYNTHETIC answer key. Never load into the app database.",
            "seed": self.seed,
            "policy": self.policy,
            "summary": self.summary(),
            "events": [{**asdict(e), "onset": e.onset.isoformat()} for e in self.events],
            "invoices": {k: asdict(v) for k, v in self.truths.items()},
        }


# ------------------------------------------------------------------------------------------ helpers
@dataclass
class _Draft:
    """An invoice before ids are assigned (ids follow date order)."""

    association_id: str
    trade: str
    invoice_date: date
    amount: float
    memo: str
    fund_booked: str
    truth: InvoiceTruth
    vendor: tuple[str, ...] | None = None  # pinned vendor (projects keep one contractor)


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's method; fine for the small rates used here."""
    if lam <= 0:
        return 0
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def _wear(age_fraction: float) -> float:
    """Repair-rate multiplier: low when new, rising steeply past the end of useful life."""
    return min(0.4 + 2.6 * max(age_fraction, 0.0) ** 3, 6.0)


def _rand_date(rng: random.Random, year: int, months: tuple[int, ...] = tuple(range(1, 13))) -> date:
    month = rng.choice(months)
    day = rng.randint(1, 28)
    return date(year, month, day)


def _inflate(cost: float, rate: float, year: int) -> float:
    return cost * (1 + rate) ** (year - STUDY_YEAR)


def _money(x: float) -> float:
    return round(x, 2)


def _letters(n: int) -> list[str]:
    return [chr(ord("A") + i) for i in range(n)]


# --------------------------------------------------------------------------------------- generator
class _Generator:
    def __init__(self, seed: int, n_associations: int):
        self.seed = seed
        self.rng = random.Random(seed)
        self.n = n_associations
        self.portfolios: list[SynthPortfolio] = []
        self.associations: list[SynthAssociation] = []
        self.components: list[SynthComponent] = []
        self.specs: dict[str, ComponentSpec] = {}  # component id -> spec
        self.events: list[PlantedEvent] = []
        self.event_by_component: dict[str, PlantedEvent] = {}
        self.drafts: list[_Draft] = []
        self.project_seq = 0

    # ---- structure
    def build_structure(self) -> None:
        rng = self.rng
        self.portfolios = [SynthPortfolio(f"P{i + 1:02d}", name) for i, name in enumerate(PORTFOLIO_NAMES)]
        kinds = [k for k, _ in zip(["condo_midrise", "garden", "sfh_hoa"] * self.n, range(self.n), strict=False)]
        rng.shuffle(kinds)
        stems = rng.sample(NAME_STEMS, self.n)
        for i, kind_name in enumerate(kinds):
            kind = KINDS[kind_name]
            assoc_id = f"A{i + 1:02d}"
            self._build_association(assoc_id, self.portfolios[i % len(self.portfolios)].id, kind, stems[i])

    def _build_association(self, assoc_id: str, portfolio_id: str, kind: KindSpec, stem: str) -> None:
        rng = self.rng
        units = rng.randint(*kind.units)
        buildings = rng.randint(*kind.buildings)
        year_built = rng.randint(*kind.year_built)
        inflation = round(rng.uniform(0.025, 0.035), 4)
        locations = [f"Bldg {x}" for x in _letters(buildings)]

        fully_funded, annual_need = 0.0, 0.0
        for spec in kind.components:
            places = locations if spec.per_building and buildings > 1 else [None]
            for loc in places:
                cost = (spec.base_cost + spec.per_unit_cost * units) / len(places) * rng.uniform(0.85, 1.15)
                cost = round(cost, -2)
                age = (STUDY_YEAR - year_built) % spec.useful_life
                remaining = min(max(spec.useful_life - age + rng.randint(-2, 2), 1), spec.useful_life)
                suffix = f"-{loc.split()[-1]}" if loc else ""
                comp = SynthComponent(
                    id=f"{assoc_id}-{spec.code}{suffix}",
                    association_id=assoc_id,
                    category=spec.category,
                    name=spec.name,
                    location=loc,
                    useful_life_years=spec.useful_life,
                    remaining_life_years=remaining,
                    replacement_cost=cost,
                    planned_year=STUDY_YEAR + remaining,
                )
                self.components.append(comp)
                self.specs[comp.id] = spec
                fully_funded += cost * (1 - remaining / spec.useful_life)
                annual_need += cost / spec.useful_life

        self.associations.append(
            SynthAssociation(
                id=assoc_id,
                portfolio_id=portfolio_id,
                name=f"{stem} {rng.choice(kind.name_suffixes)}",
                kind=kind.kind,
                town=rng.choice(TOWNS),
                units=units,
                buildings=buildings,
                year_built=year_built,
                study_year=STUDY_YEAR,
                inflation_rate=inflation,
                reserve_balance_start=round(fully_funded * rng.uniform(0.3, 0.8), -3),
                annual_contribution=round(annual_need * rng.uniform(0.6, 1.1), -2),
            )
        )

    # ---- planted problems
    def plant_events(self) -> None:
        rng = self.rng
        used_assocs: Counter[str] = Counter()

        def pick(ok) -> SynthComponent | None:
            pool = [c for c in self.components if c.id not in self.event_by_component and ok(c)]
            if not pool:
                return None
            # Prefer associations with fewer events so problems spread across the portfolio.
            low = min(used_assocs[c.association_id] for c in pool)
            return rng.choice([c for c in pool if used_assocs[c.association_id] == low])

        rules = {
            # Long-lived parts not due until late in (or after) the history: an early failure is news.
            "early_failure": lambda c: c.useful_life_years >= 12 and c.planned_year >= LAST_YEAR + 2,
            "cost_overrun": lambda c: (
                FIRST_YEAR + 1 <= c.planned_year <= LAST_YEAR - 1 and c.replacement_cost >= 20_000
            ),
            "deferred": lambda c: FIRST_YEAR + 1 <= c.planned_year <= LAST_YEAR - 3 and c.useful_life_years >= 10,
            "miscoded": lambda c: FIRST_YEAR + 1 <= c.planned_year <= LAST_YEAR - 1 and c.useful_life_years >= 10,
        }
        n = 0
        for etype, count in EVENT_PLAN.items():
            for _ in range(count):
                comp = pick(rules[etype])
                if comp is None:
                    continue
                n += 1
                event = self._describe_event(f"E{n:02d}", etype, comp)
                self.events.append(event)
                self.event_by_component[comp.id] = event
                used_assocs[comp.association_id] += 1

    def _describe_event(self, event_id: str, etype: str, comp: SynthComponent) -> PlantedEvent:
        rng = self.rng
        where = f"{comp.name}{' (' + comp.location + ')' if comp.location else ''}"
        if etype == "early_failure":
            onset = _rand_date(rng, rng.randint(2019, 2022))
            text = f"{where} starts failing in {onset:%b %Y}, years before its planned {comp.planned_year} replacement."
        elif etype == "cost_overrun":
            onset = date(comp.planned_year, 1, 1)
            text = f"{where} replacement in {comp.planned_year} runs 30-60% over the reserve study."
        elif etype == "deferred":
            onset = date(comp.planned_year, 12, 31)
            text = f"{where} was due in {comp.planned_year} but never replaced; repairs keep growing."
        else:
            onset = date(comp.planned_year, 1, 1)
            text = f"{where} replacement in {comp.planned_year} was booked to the operating fund."
        return PlantedEvent(event_id, etype, comp.association_id, comp.id, onset, text)

    # ---- component history
    def component_history(self, comp: SynthComponent, assoc: SynthAssociation) -> None:
        rng = self.rng
        spec = self.specs[comp.id]
        event = self.event_by_component.get(comp.id)
        etype = event.type if event else None

        # Replacement dates within the history window.
        replacements: list[date] = []
        fail_end = HISTORY_END  # end of the failing period: the emergency replacement, if it happens
        if etype == "early_failure":
            fail = event.onset + timedelta(days=rng.randint(540, 3 * 365))
            if fail <= date(LAST_YEAR, 9, 30):
                replacements.append(fail)
                fail_end = fail
        else:
            due = comp.planned_year
            first = True
            while due <= LAST_YEAR:
                if not (first and etype == "deferred"):
                    replacements.append(_rand_date(rng, due, (4, 5, 6, 7, 8, 9, 10)))
                first = False
                due += spec.useful_life

        for i, when in enumerate(replacements):
            overrun = rng.uniform(1.3, 1.6) if (etype == "cost_overrun" and i == 0) else 1.0
            miscoded = etype == "miscoded" and i == 0
            tagged = event if (event and i == 0 and etype != "deferred") else None
            self._project(comp, spec, assoc, when, overrun, miscoded, tagged)

        # Repairs, year by year, with the rate tied to age since the last replacement.
        age0 = spec.useful_life - comp.remaining_life_years
        for year in range(FIRST_YEAR, LAST_YEAR + 1):
            last = max([r for r in replacements if r.year < year], default=None)
            age = (year - last.year) if last else age0 + (year - STUDY_YEAR)
            rate = (0.3 if spec.per_building else 0.5) * _wear(age / spec.useful_life)
            for _ in range(_poisson(rng, rate)):
                when = _rand_date(rng, year)
                if etype == "early_failure" and event.onset <= when <= fail_end:
                    continue  # the failing period gets its own, heavier repair stream below
                tagged = event if (etype == "deferred" and when > event.onset) else None
                self._repair(comp, spec, assoc, when, 1.0, tagged)
            # Occasional big partial replacement: the ambiguous cases.
            if rng.random() < 0.05 * _wear(age / spec.useful_life):
                self._partial(comp, spec, assoc, _rand_date(rng, year))

        if etype == "early_failure":
            # Between onset and the emergency replacement (or the end of the history), repairs come
            # about four a year and cost 1.6x normal. At least three, so the signal is always there.
            span = (fail_end - event.onset).days
            for _ in range(max(_poisson(rng, 4.0 * span / 365), 3)):
                when = event.onset + timedelta(days=rng.randint(0, max(span - 1, 0)))
                self._repair(comp, spec, assoc, when, 1.6, event)

    def _location_text(self, comp: SynthComponent, assoc: SynthAssociation) -> str:
        """Location as a memo writes it, sometimes with the wrong building (a real data-entry error)."""
        if not comp.location:
            return ""
        loc = comp.location
        if assoc.buildings > 1 and self.rng.random() < 0.05:
            wrong = [f"Bldg {x}" for x in _letters(assoc.buildings) if f"Bldg {x}" != loc]
            loc = self.rng.choice(wrong)
        return self.rng.choice([loc, loc.replace("Bldg ", "Bldg. "), loc.replace("Bldg ", "Building ")])

    def _repair(self, comp, spec, assoc, when: date, factor: float, event: PlantedEvent | None) -> None:
        rng = self.rng
        amount = _inflate(comp.replacement_cost, assoc.inflation_rate, when.year) * rng.uniform(0.004, 0.02)
        amount = max(amount * factor, 150.0)
        word = rng.choice(spec.repair_words)
        loc = self._location_text(comp, assoc)
        secondary = None
        sibling = [
            c
            for c in self.components
            if c.association_id == comp.association_id
            and c.id != comp.id
            and c.location == comp.location
            and self.specs[c.id].trade == spec.trade
        ]
        if sibling and rng.random() < 0.08:
            other = rng.choice(sibling)
            secondary = other.id
            first, second = (n.split("(")[0].strip() for n in (spec.name, self.specs[other.id].name))
            memo = f"{first} and {second.lower()} repair {loc}".strip()
        else:
            templates = [
                "{word} - {loc}",
                "Service call: {word} ({loc})",
                "Repair {word} {loc}",
                "{loc} {word}",
                "T&M {word}",
                "Emergency call - {word} {loc}",
                "Service call {loc}",
                "Labor and materials per ticket",
            ]
            weights = [5, 4, 4, 3, 2, 2, 1, 1]
            memo = rng.choices(templates, weights)[0].format(word=word, loc=loc).strip(" -()")
        self.drafts.append(
            _Draft(
                assoc.id,
                spec.trade,
                when,
                _money(amount),
                memo,
                "operating",
                InvoiceTruth("operating", "repair", comp.id, secondary, event_id=event.id if event else None),
            )
        )

    def _partial(self, comp, spec, assoc, when: date) -> None:
        rng = self.rng
        share = rng.uniform(0.06, CAPITAL_THRESHOLD - 0.01)
        amount = _inflate(comp.replacement_cost, assoc.inflation_rate, when.year) * share
        phrase = rng.choice(spec.replace_words)
        loc = self._location_text(comp, assoc)
        section = f" - section {loc}" if loc else ""
        memo = rng.choice(
            [
                f"Partial {phrase}{section}",
                f"{phrase.capitalize()} (phase 1 of ?) {loc}",
                f"Major repair - {rng.choice(spec.repair_words)} incl. new materials {loc}",
            ]
        ).strip()
        self.drafts.append(
            _Draft(
                assoc.id,
                spec.trade,
                when,
                _money(amount),
                memo,
                rng.choice(["operating", "reserve"]),
                InvoiceTruth(
                    "operating",
                    "repair",
                    comp.id,
                    ambiguous=True,
                    note=f"Partial work at {share:.0%} of replacement cost, under the {CAPITAL_THRESHOLD:.0%} capital "
                    "threshold, so policy treats it as a repair; wording suggests a replacement.",
                ),
            )
        )

    def _project(
        self, comp, spec, assoc, when: date, overrun: float, miscoded: bool, event: PlantedEvent | None
    ) -> None:
        rng = self.rng
        self.project_seq += 1
        project_id = f"PRJ-{self.project_seq:04d}"
        contract = str(rng.randint(1000, 9999))
        total = _inflate(comp.replacement_cost, assoc.inflation_rate, when.year) * rng.uniform(0.9, 1.12) * overrun
        phrase = rng.choice(spec.replace_words)
        loc = self._location_text(comp, assoc)
        fund = "operating" if miscoded else "reserve"
        vendor = rng.choice(VENDORS[spec.trade])

        if total <= PROJECT_SPLIT_THRESHOLD:
            parts = [(when, total, f"{phrase.capitalize()} {loc}".strip())]
        else:
            deposit_share = rng.uniform(0.3, 0.4)
            parts = [
                (
                    when - timedelta(days=rng.randint(21, 60)),
                    total * deposit_share,
                    f"Deposit per contract {contract} - {phrase} {loc}".strip(),
                )
            ]
            remaining = total * (1 - deposit_share)
            if total > 150_000:
                progress = remaining * rng.uniform(0.4, 0.6)
                parts.append((when, progress, f"Progress billing #1 contract {contract}"))
                remaining -= progress
            parts.append(
                (
                    when + timedelta(days=rng.randint(20, 75)),
                    remaining,
                    rng.choice(
                        [
                            f"Balance due - contract {contract}",
                            f"Final invoice #{contract}",
                            f"Retainage release {contract}",
                        ]
                    ),
                )
            )
        for d, amount, memo in parts:
            d = min(d, HISTORY_END)
            self.drafts.append(
                _Draft(
                    assoc.id,
                    spec.trade,
                    d,
                    _money(amount),
                    memo,
                    fund,
                    InvoiceTruth(
                        "reserve", "replacement", comp.id, project_id=project_id, event_id=event.id if event else None
                    ),
                    vendor=vendor,
                )
            )

    # ---- routine services
    def routine(self, assoc: SynthAssociation) -> None:
        rng = self.rng
        size = (assoc.units / 150) ** 0.7
        for trade, templates, typical, per_year in ROUTINE_SERVICES:
            for year in range(FIRST_YEAR, LAST_YEAR + 1):
                for _ in range(_poisson(rng, per_year[assoc.kind])):
                    months = (
                        (12, 1, 2, 3)
                        if trade == "snow"
                        else ((4, 5, 6, 7, 8, 9, 10, 11) if trade == "landscape" else tuple(range(1, 13)))
                    )
                    when = _rand_date(rng, year, months)
                    memo = rng.choice(templates).format(month=f"{when:%b %Y}", day=f"{when.month}/{when.day}")
                    amount = (
                        typical * size * rng.uniform(0.85, 1.15) * (1 + assoc.inflation_rate) ** (year - STUDY_YEAR)
                    )
                    self.drafts.append(
                        _Draft(
                            assoc.id,
                            trade,
                            when,
                            _money(amount),
                            memo,
                            "operating",
                            InvoiceTruth("operating", "routine"),
                        )
                    )

    # ---- finish
    def finish(self) -> tuple[list[SynthInvoice], dict[str, InvoiceTruth]]:
        rng = self.rng
        # Vendors per association: each association uses one vendor per trade most of the time.
        assoc_vendor: dict[tuple[str, str], tuple[str, ...]] = {}
        counters: Counter[str] = Counter()
        self.drafts.sort(key=lambda d: (d.invoice_date, d.association_id, d.memo, d.amount))
        invoices, truths = [], {}
        for i, d in enumerate(self.drafts, start=1):
            vendor = d.vendor
            if vendor is None:
                key = (d.association_id, d.trade)
                if key not in assoc_vendor or rng.random() < 0.1:
                    assoc_vendor[key] = rng.choice(VENDORS[d.trade])
                vendor = assoc_vendor[key]
            name = rng.choice(vendor)
            prefix = "".join(w[0] for w in vendor[0].split() if w[0].isalpha())[:3].upper()
            counters[prefix] += 1
            inv_id = f"INV-{i:06d}"
            invoices.append(
                SynthInvoice(
                    inv_id,
                    d.association_id,
                    name,
                    f"{prefix}-{1000 + counters[prefix]}",
                    d.invoice_date,
                    d.amount,
                    d.memo,
                    d.fund_booked,
                )
            )
            truths[inv_id] = d.truth
        return invoices, truths


def generate(seed: int = 7, n_associations: int = 20) -> tuple[SynthDataset, AnswerKey]:
    """Build a synthetic portfolio and its answer key. Same seed, same output."""
    g = _Generator(seed, n_associations)
    g.build_structure()
    g.plant_events()
    by_id = {a.id: a for a in g.associations}
    for comp in g.components:
        g.component_history(comp, by_id[comp.association_id])
    for assoc in g.associations:
        g.routine(assoc)
    invoices, truths = g.finish()
    dataset = SynthDataset(seed, g.portfolios, g.associations, g.components, invoices)
    return dataset, AnswerKey(seed, truths, g.events)
