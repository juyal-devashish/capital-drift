"""Reserve study PDFs: what the app reads back must equal what the generator wrote."""

from dataclasses import replace

import pytest
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.parsers.reserve_study_pdf import HEADER, parse_reserve_study
from app.synth.generator import generate
from app.synth.io import STUDIES_DIR, load_dataset, write_dataset
from app.synth.report_pdf import COLUMNS, write_all, write_study_pdf


@pytest.fixture(scope="module")
def portfolio(tmp_path_factory):
    dataset, _ = generate(seed=7)
    out = tmp_path_factory.mktemp("studies")
    write_all(dataset.associations, dataset.components, out)
    return dataset, out


def _expected(dataset, assoc_id):
    return {
        c.id.split("-", 1)[1]: (
            c.name,
            c.category,
            c.location,
            c.useful_life_years,
            c.remaining_life_years,
            c.replacement_cost,
            c.planned_year,
        )
        for c in dataset.components
        if c.association_id == assoc_id
    }


def test_every_study_reads_back_exactly(portfolio):
    dataset, out = portfolio
    for assoc in dataset.associations:
        study = parse_reserve_study(out / f"{assoc.id}.pdf")
        assert study.warnings == [], assoc.id
        got = {
            c.ref: (
                c.name,
                c.category,
                c.location,
                c.useful_life_years,
                c.remaining_life_years,
                c.replacement_cost,
                c.planned_year,
            )
            for c in study.components
        }
        assert got == _expected(dataset, assoc.id)
        assert study.funding == {
            "reserve_balance_start": assoc.reserve_balance_start,
            "annual_contribution": assoc.annual_contribution,
            "inflation_rate": assoc.inflation_rate,
        }


def test_rows_carry_their_page_and_position(portfolio):
    dataset, out = portfolio
    study = parse_reserve_study(out / f"{dataset.associations[0].id}.pdf")
    for c in study.components:
        assert c.page == 2  # the cover is page 1; inventories here fit on one page
        x0, top, x1, bottom = c.bbox
        assert 0 < x0 < x1 < 792 and 0 < top < bottom < 612


def test_long_inventory_continues_across_pages(tmp_path):
    dataset, _ = generate(seed=7)
    assoc = dataset.associations[0]
    base = [c for c in dataset.components if c.association_id == assoc.id]
    many = [replace(base[i % len(base)], id=f"{assoc.id}-X{i:03d}") for i in range(75)]
    path = tmp_path / "long.pdf"
    write_study_pdf(assoc, many, path)
    study = parse_reserve_study(path)
    assert study.warnings == []
    assert [c.ref for c in study.components] == [f"X{i:03d}" for i in range(75)]
    assert {c.page for c in study.components} == {2, 3, 4}


def test_same_input_same_pdf_bytes(tmp_path):
    dataset, _ = generate(seed=7)
    write_all(dataset.associations[:2], dataset.components, tmp_path / "a")
    write_all(dataset.associations[:2], dataset.components, tmp_path / "b")
    for name in ("A01.pdf", "A02.pdf"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def _damaged_study(path):
    """A study whose second row has a cost the reader can't use, and no funding summary."""
    c = canvas.Canvas(str(path), pagesize=landscape(letter))
    y = 500
    for word, x in COLUMNS:
        c.drawString(x, y, word)
    rows = [
        ("ROOF", "Roof membrane", "Roofing", "-", "20", "5", "$60,000", "2021"),
        ("BOIL", "Boiler plant", "Mechanical", "-", "25", "9", "TBD", "2025"),
    ]
    for row in rows:
        y -= 15
        for (_, x), text in zip(COLUMNS, row, strict=True):
            c.drawString(x, y, text)
    c.save()


def test_a_bad_row_is_a_warning_not_a_silent_skip(tmp_path):
    path = tmp_path / "bad.pdf"
    _damaged_study(path)
    study = parse_reserve_study(path)
    assert [c.ref for c in study.components] == ["ROOF"]
    assert any("BOIL" in w and "not an amount" in w for w in study.warnings)
    assert any("inflation rate" in w for w in study.warnings)


def test_loader_refuses_a_study_it_could_not_read_cleanly(env, tmp_path):
    from app.db.session import session_scope

    out = tmp_path / "synth"
    write_dataset(*generate(seed=3, n_associations=3), out)
    _damaged_study(out / STUDIES_DIR / "A02.pdf")
    with pytest.raises(ValueError, match="A02.pdf"), session_scope() as db:
        load_dataset(db, out)


def test_pdf_and_csv_loads_give_identical_rows(env, tmp_path):
    from app.db.models import Association, ReserveComponent
    from app.db.session import session_scope

    out = tmp_path / "synth"
    write_dataset(*generate(seed=5, n_associations=6), out)

    def snapshot():
        with session_scope() as db:
            comps = [
                (
                    c.id,
                    c.association_id,
                    c.category,
                    c.name,
                    c.location,
                    c.useful_life_years,
                    c.remaining_life_years,
                    c.replacement_cost,
                    c.planned_year,
                )
                for c in db.scalars(select(ReserveComponent).order_by(ReserveComponent.id))
            ]
            funding = [
                (a.id, a.reserve_balance_start, a.annual_contribution, a.inflation_rate)
                for a in db.scalars(select(Association).order_by(Association.id))
            ]
        return comps, funding

    with session_scope() as db:
        load_dataset(db, out, studies="csv")
    from_csv = snapshot()
    with session_scope() as db:
        load_dataset(db, out, studies="pdf")
    assert snapshot() == from_csv
    assert len(from_csv[0]) > 0


def test_writer_and_reader_agree_on_the_columns():
    assert tuple(word for word, _ in COLUMNS) == HEADER
