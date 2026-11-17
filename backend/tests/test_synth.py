"""Synthetic portfolio generator: determinism, integrity, the planted problems and the load path."""

import hashlib
from collections import defaultdict
from datetime import date

import pytest
from sqlalchemy import func, inspect, select

from app.synth.generator import CAPITAL_THRESHOLD, EVENT_PLAN, generate
from app.synth.io import ANSWER_KEY, load_dataset, write_dataset


@pytest.fixture(scope="module")
def data():
    return generate(seed=7)


def _digest(directory) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(directory)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def test_same_seed_same_files_different_seed_different_files(tmp_path):
    for name, seed in (("a", 7), ("b", 7), ("c", 8)):
        write_dataset(*generate(seed=seed), tmp_path / name)
    assert _digest(tmp_path / "a") == _digest(tmp_path / "b")
    assert _digest(tmp_path / "a") != _digest(tmp_path / "c")


def test_shape_and_mix(data):
    dataset, key = data
    assert len(dataset.portfolios) == 3
    assert len(dataset.associations) == 20
    assert {a.kind for a in dataset.associations} == {"condo_midrise", "garden", "sfh_hoa"}
    assert len({a.name for a in dataset.associations}) == 20
    n = len(dataset.invoices)
    assert 2_500 <= n <= 4_500
    by_type = defaultdict(int)
    for t in key.truths.values():
        by_type[t.work_type] += 1
    assert 0.45 <= by_type["routine"] / n <= 0.70
    assert 0.25 <= by_type["repair"] / n <= 0.45
    assert 0.04 <= by_type["replacement"] / n <= 0.12
    assert 0.03 <= sum(t.ambiguous for t in key.truths.values()) / n <= 0.07


def test_referential_integrity(data):
    dataset, key = data
    assoc_ids = {a.id for a in dataset.associations}
    comp_assoc = {c.id: c.association_id for c in dataset.components}
    assert len(comp_assoc) == len(dataset.components), "component ids are unique"
    assert {a.portfolio_id for a in dataset.associations} <= {p.id for p in dataset.portfolios}
    assert set(key.truths) == {i.id for i in dataset.invoices}
    for inv in dataset.invoices:
        assert inv.association_id in assoc_ids
        assert date(2015, 1, 1) <= inv.invoice_date <= date(2025, 12, 31)
        assert inv.amount > 0
        assert inv.fund_booked in {"operating", "reserve"}
        truth = key.truths[inv.id]
        for cid in (truth.component_id, truth.secondary_component_id):
            if cid:
                assert comp_assoc[cid] == inv.association_id, "an invoice only touches its own association"
        assert (truth.component_id is None) == (truth.work_type == "routine")
        assert truth.fund == ("reserve" if truth.work_type == "replacement" else "operating")
    for c in dataset.components:
        assert c.planned_year == 2016 + c.remaining_life_years
        assert 1 <= c.remaining_life_years <= c.useful_life_years


def test_ambiguous_invoices_sit_just_under_the_capital_threshold(data):
    dataset, key = data
    comps = {c.id: c for c in dataset.components}
    assocs = {a.id: a for a in dataset.associations}
    for inv in dataset.invoices:
        truth = key.truths[inv.id]
        if not truth.ambiguous:
            continue
        comp, assoc = comps[truth.component_id], assocs[inv.association_id]
        inflated = comp.replacement_cost * (1 + assoc.inflation_rate) ** (inv.invoice_date.year - 2016)
        assert 0.05 <= inv.amount / inflated < CAPITAL_THRESHOLD
        assert truth.work_type == "repair" and truth.note


def test_every_planted_problem_shows_up_in_the_invoices(data):
    dataset, key = data
    assert {e.type: 0 for e in key.events}.keys() == EVENT_PLAN.keys()
    assert len(key.events) == sum(EVENT_PLAN.values())
    assert len({e.component_id for e in key.events}) == len(key.events)
    comps = {c.id: c for c in dataset.components}
    assocs = {a.id: a for a in dataset.associations}
    invoices = {i.id: i for i in dataset.invoices}

    def lines(component_id, work_type):
        return [
            invoices[i] for i, t in key.truths.items() if t.component_id == component_id and t.work_type == work_type
        ]

    for e in key.events:
        comp = comps[e.component_id]
        repairs, projects = lines(comp.id, "repair"), lines(comp.id, "replacement")
        if e.type == "early_failure":
            # Repairs per year jump after the onset (only counting up to any replacement).
            end = min([p.invoice_date for p in projects], default=date(2025, 12, 31))
            before = [r for r in repairs if r.invoice_date < e.onset]
            after = [r for r in repairs if e.onset <= r.invoice_date <= end]
            years_before = max((e.onset - date(2016, 1, 1)).days / 365, 0.5)
            years_after = max((end - e.onset).days / 365, 0.25)
            assert len(after) / years_after > 2 * len(before) / years_before, e.description
            assert all(p.invoice_date.year < comp.planned_year for p in projects)
        elif e.type == "cost_overrun":
            assoc = assocs[comp.association_id]
            first = min(p.invoice_date for p in projects)
            first_project = [
                p
                for p in projects
                if key.truths[p.id].project_id == key.truths[min(projects, key=lambda p: p.invoice_date).id].project_id
            ]
            planned = comp.replacement_cost * (1 + assoc.inflation_rate) ** (first.year - 2016)
            # Overrun factor 1.3-1.6 times normal price noise 0.9-1.12, so at least 1.17x the plan.
            assert sum(p.amount for p in first_project) >= 1.15 * planned, e.description
        elif e.type == "deferred":
            assert not [p for p in projects if p.invoice_date.year == comp.planned_year], e.description
        elif e.type == "miscoded":
            tagged = [p for p in projects if key.truths[p.id].event_id == e.id]
            assert tagged and all(p.fund_booked == "operating" for p in tagged), e.description


def test_load_puts_only_client_data_in_the_database(env, tmp_path):
    from app.db.models import Association, Invoice, Portfolio, ReserveComponent
    from app.db.session import get_engine, session_scope

    out = tmp_path / "synth"
    written = write_dataset(*generate(seed=3, n_associations=6), out)
    with session_scope() as db:
        loaded = load_dataset(db, out)
    assert loaded["invoices.csv"] == written["invoices.csv"]
    assert loaded["reserve_components"] == written["reserve_study.csv"]
    assert loaded["reserve_studies"] == written["reserve_studies"] == 6

    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Portfolio)) == 3
        assert db.scalar(select(func.count()).select_from(Association)) == 6
        assert db.scalar(select(func.count()).select_from(ReserveComponent)) == written["reserve_study.csv"]
        assert db.scalar(select(func.count()).select_from(Invoice)) == written["invoices.csv"]
        inv = db.scalars(select(Invoice).order_by(Invoice.id)).first()
        assert isinstance(inv.invoice_date, date)

    # No column anywhere in the capital tables carries the answer key.
    insp = inspect(get_engine())
    truth_words = {"truth", "component_id", "work_type", "event", "ambiguous", "project"}
    for table in ("portfolios", "associations", "reserve_components", "invoices"):
        cols = {c["name"] for c in insp.get_columns(table)}
        assert not cols & truth_words, (table, cols & truth_words)

    # Loading again replaces rather than duplicates.
    with session_scope() as db:
        load_dataset(db, out)
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Invoice)) == written["invoices.csv"]


def test_load_fails_loudly_on_a_missing_file(env, tmp_path):
    from app.db.session import session_scope

    out = tmp_path / "synth"
    write_dataset(*generate(seed=3, n_associations=3), out)
    (out / "invoices.csv").unlink()
    assert (out / ANSWER_KEY).exists()
    with pytest.raises(FileNotFoundError), session_scope() as db:
        load_dataset(db, out)
