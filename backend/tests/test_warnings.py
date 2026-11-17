"""Repair-or-replace warnings: the three checks, no lookahead, and regression floors on synthetic seeds."""

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import pytest

from app.domain.warnings import Spend, WatchSettings, in_control_years, spend_from_matches, watch_spend
from app.evals.warnings import evaluate_seed, truth_matches


@dataclass
class Comp:
    id: str
    association_id: str = "G"
    name: str = "Roof"
    location: str | None = None
    useful_life_years: int = 20
    remaining_life_years: int = 10
    replacement_cost: float = 100_000.0
    planned_year: int = 2026
    category: str = "roofing"


@dataclass
class Assoc:
    id: str = "G"
    study_year: int = 2016
    inflation_rate: float = 0.0


START, END = date(2016, 1, 1), date(2025, 12, 31)


def _watch(comps, spend, through=END, **settings):
    return watch_spend(comps, [Assoc()], spend, START, through, WatchSettings(**settings))


def _quiet_portfolio(n=40):
    """Healthy parts with one repair every other year, so the usual rate is about 0.5 a year."""
    comps = [Comp(f"C{i:02d}") for i in range(n)]
    spend = [
        Spend(f"R{i}-{y}", c.id, date(y, 1 + i % 12, 10), 800.0, "repair")
        for i, c in enumerate(comps)
        for y in range(2016 + i % 2, 2026, 2)
    ]
    return comps, spend


def test_a_burst_of_repairs_on_a_part_due_years_out_is_failing_early():
    comps, spend = _quiet_portfolio()
    burst = [Spend(f"B{k}", "C00", date(2021, 1 + k, 5), 1_500.0, "repair") for k in range(8)]
    warnings = _watch(comps, spend + burst)
    early = [w for w in warnings if w.kind == "failing_early"]
    assert [w.component_id for w in early] == ["C00"]
    w = early[0]
    assert date(2021, 3, 1) <= w.fired_on <= date(2021, 8, 31)
    assert w.numbers["planned_year"] == 2026 and w.numbers["repairs_since_climb"] >= 4
    assert set(w.invoice_ids) >= {x.invoice_id for x in burst if x.on <= w.fired_on}
    assert "replaces it in 2026" in w.message


def test_no_failing_early_warning_when_the_plan_already_replaces_it_next_year():
    comps, spend = _quiet_portfolio()
    comps[0].planned_year = 2022
    burst = [Spend(f"B{k}", "C00", date(2021, 1 + k, 5), 1_500.0, "repair") for k in range(8)]
    assert not [w for w in _watch(comps, spend + burst) if w.kind == "failing_early"]


def test_overdue_fires_after_the_grace_period_and_not_once_replaced():
    late = Comp("LATE", planned_year=2019)
    done = Comp("DONE", planned_year=2019)
    spend = [
        Spend("D1", "DONE", date(2019, 5, 1), 40_000.0, "replacement"),  # deposit alone isn't done
        Spend("D2", "DONE", date(2019, 7, 1), 65_000.0, "replacement"),
        Spend("L1", "LATE", date(2021, 2, 1), 900.0, "repair"),
    ]
    warnings = _watch([late, done], spend)
    assert [(w.kind, w.component_id, w.fired_on) for w in warnings] == [("overdue", "LATE", date(2020, 3, 31))]
    assert warnings[0].numbers["planned_year"] == 2019


def test_a_deposit_alone_does_not_count_as_a_replacement():
    comp = Comp("DEP", planned_year=2019)
    warnings = _watch([comp], [Spend("D1", "DEP", date(2019, 5, 1), 35_000.0, "replacement")])
    assert [w.kind for w in warnings] == ["overdue"]
    assert warnings[0].fired_on > date(2019, 5, 1) + timedelta(days=180)


def test_over_budget_fires_on_the_invoice_that_crosses_the_contingency():
    comp = Comp("OVR", planned_year=2020, replacement_cost=100_000.0)
    near = Comp("NEAR", planned_year=2020, replacement_cost=100_000.0)
    spend = [
        Spend("O1", "OVR", date(2020, 4, 1), 40_000.0, "replacement"),
        Spend("O2", "OVR", date(2020, 6, 1), 70_000.0, "replacement"),  # 110%: inside the contingency
        Spend("O3", "OVR", date(2020, 11, 20), 20_000.0, "replacement"),  # 130%: the final bill
        Spend("N1", "NEAR", date(2020, 6, 1), 112_000.0, "replacement"),
    ]
    warnings = _watch([comp, near], spend)
    assert [(w.kind, w.component_id, w.fired_on) for w in warnings] == [("over_budget", "OVR", date(2020, 11, 20))]
    assert warnings[0].numbers["over_share"] == pytest.approx(0.30)
    assert warnings[0].invoice_ids == ["O1", "O2", "O3"]


def test_a_replacement_starts_a_new_cycle_with_a_new_due_year():
    comp = Comp("SEAL", useful_life_years=5, remaining_life_years=1, replacement_cost=10_000.0, planned_year=2017)
    spend = [Spend("S1", "SEAL", date(2017, 6, 1), 10_000.0, "replacement")]
    warnings = _watch([comp], spend)
    assert [(w.kind, w.numbers["planned_year"], w.fired_on) for w in warnings] == [("overdue", 2022, date(2023, 3, 31))]


def test_warnings_never_use_spend_after_the_day_they_fire():
    """Replaying a truncated history gives exactly the full run's warnings up to that day."""
    from app.synth.generator import generate

    ds, key = generate(5, n_associations=8)
    spend = spend_from_matches(truth_matches({k: asdict(v) for k, v in key.truths.items()}), ds.invoices)
    full = watch_spend(ds.components, ds.associations, spend, START, END)
    assert len(full) >= 5
    for cut in (date(2019, 6, 30), date(2021, 3, 31), date(2023, 10, 31)):
        upto = [x for x in spend if x.on <= cut]
        part = watch_spend(ds.components, ds.associations, upto, START, cut)
        assert part == [w for w in full if w.fired_on <= cut], cut


def test_the_default_threshold_keeps_healthy_parts_quiet_for_centuries():
    assert in_control_years(0.5, runs=400) >= 400
    assert in_control_years(1.0, runs=400) >= 300


# Regression floors: measured 2026-11-17 (docs/results.md). Never lower them to make a change pass.
@pytest.mark.parametrize(
    ("seed", "labels", "min_detected", "max_false"),
    [(7, "truth", 12, 1), (7, "rules", 11, 12), (11, "rules", 8, 21)],
)
def test_regression_floors(seed, labels, min_detected, max_false):
    r = evaluate_seed(seed, labels)
    assert r["detected"] >= min_detected
    assert r["false_alarms"] <= max_false
    assert r["events"]["deferred"]["detected"] == r["events"]["deferred"]["planted"]
    assert r["events"]["cost_overrun"]["detected"] == r["events"]["cost_overrun"]["planted"]


def test_service_stores_warnings_per_method(env, tmp_path):
    from sqlalchemy import func, select

    from app.db.models import SpendWarningRecord
    from app.db.session import session_scope
    from app.services.matching import run_rule_matching
    from app.services.warnings import run_warnings, stored_warnings
    from app.synth.generator import generate
    from app.synth.io import load_dataset, write_dataset

    out = tmp_path / "synth"
    write_dataset(*generate(seed=5, n_associations=8), out)
    with session_scope() as db:
        load_dataset(db, out)
    with session_scope() as db:
        run_rule_matching(db)
    with session_scope() as db:
        report = run_warnings(db, "rules")
        again = run_warnings(db, "rules")
    assert report == again and report["warnings"] > 0
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(SpendWarningRecord)) == report["warnings"]
        assert len(stored_warnings(db, "rules")) == report["warnings"]
        load_dataset(db, out)  # reloading clears warnings along with matches
        assert db.scalar(select(func.count()).select_from(SpendWarningRecord)) == 0
