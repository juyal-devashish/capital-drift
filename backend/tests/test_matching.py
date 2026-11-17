"""Rule-based invoice matching: the individual rules, the guarantees, and accuracy floors.

Floors come from seed 7 (the seed the rules were tuned on) and seed 11 (held out, never tuned on),
measured on 2026-11-16. Never lower them to make a change pass; fix the change instead.
"""

import ast
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.domain.matching import match_invoices, memo_building, memo_terms, vendor_trade
from app.evals.matching import score_matches
from app.synth.generator import generate


@dataclass
class Inv:
    id: str
    association_id: str
    vendor_name: str
    invoice_date: date
    amount: float
    memo: str
    fund_booked: str = "operating"


@dataclass
class Comp:
    id: str
    association_id: str
    category: str
    name: str
    location: str | None
    replacement_cost: float


@dataclass
class Assoc:
    id: str
    study_year: int = 2016
    inflation_rate: float = 0.0


GARDEN = [
    Comp("G-ROOF-A", "G", "roofing", "Asphalt shingle roof", "Bldg A", 100_000),
    Comp("G-ROOF-B", "G", "roofing", "Asphalt shingle roof", "Bldg B", 100_000),
    Comp("G-GUTTER-A", "G", "roofing", "Gutters and downspouts", "Bldg A", 10_000),
    Comp("G-SEAL", "G", "paving", "Asphalt sealcoat and striping", None, 20_000),
    Comp("G-PAINT", "G", "envelope", "Exterior trim paint", None, 30_000),
    Comp("G-POND", "G", "site", "Retention pond dredging", None, 50_000),
]


def _one(memo, vendor="Keystone Roofing", amount=1_000.0, fund="operating", comps=GARDEN):
    inv = Inv("I1", "G", vendor, date(2020, 5, 1), amount, memo, fund)
    return match_invoices([inv], comps, [Assoc("G")])[0]


@pytest.mark.parametrize(
    ("vendor", "trade"),
    [
        ("KEYSTONE ROOFING", "roofing"),
        ("Brandywine Plbg", "plumbing"),
        ("Liberty Lift Services Inc", "elevator"),
        ("Rt 1 Paving", "paving"),
        ("Cresheim Grounds Co", "landscape"),
        ("SPOTLESS COMMONS", "janitorial"),
        ("Acme Holdings", None),
    ],
)
def test_vendor_trade(vendor, trade):
    assert vendor_trade(vendor) == trade


def test_building_reading():
    assert memo_building("leak at valley Bldg. C") == "Bldg C"
    assert memo_building("Service call Building d") == "Bldg D"
    assert memo_building("Landscape contract") is None


def test_lexicon_matches_whole_words_only():
    assert "trim" not in memo_terms("Mowing/trimming Jul 2020")
    assert "roof" in memo_terms("missing shingles")


def test_routine_wording_wins_over_a_lookalike_word():
    r = _one("Mowing/trimming Jul 2020", vendor="Green Valley Landscaping", amount=2_500)
    assert (r.label, r.component_id) == ("routine", None)


def test_building_picks_the_component():
    r = _one("missing shingles Bldg B")
    assert (r.label, r.component_id) == ("repair", "G-ROOF-B")


def test_no_building_and_two_lookalikes_is_unsure():
    r = _one("missing shingles")
    assert r.label == "unsure" and r.component_id is None


def test_longer_memo_word_still_matches():
    r = _one("Full lot sealcoating", vendor="Route 1 Paving", amount=18_000)
    assert (r.label, r.component_id) == ("replacement", "G-SEAL")


def test_landscaper_doing_pond_work_is_not_routine():
    r = _one("erosion at bank", vendor="Cresheim Grounds", amount=900)
    assert (r.label, r.component_id) == ("repair", "G-POND")


def test_capital_threshold_splits_repair_from_replacement():
    assert _one("roof leak Bldg A", amount=14_000).label == "repair"
    assert _one("roof leak Bldg A", amount=15_000).label == "replacement"


def test_replacement_wording_under_the_threshold_is_flagged_not_promoted():
    r = _one("Partial roof replacement - section Bldg A", amount=9_000)
    assert r.label == "repair"
    assert "wording_says_replacement" in r.flags


def test_contract_follow_ups_inherit_the_deposit_component():
    invs = [
        Inv(
            "D",
            "G",
            "Keystone Roofing",
            date(2020, 4, 1),
            35_000,
            "Deposit per contract 4471 - roof replacement Bldg B",
            "reserve",
        ),
        Inv("F", "G", "KEYSTONE ROOFING & S/M", date(2020, 6, 1), 60_000, "Final invoice #4471", "reserve"),
        Inv("X", "H", "Keystone Roofing", date(2020, 6, 1), 60_000, "Final invoice #4471", "reserve"),
    ]
    results = {r.invoice_id: r for r in match_invoices(invs, GARDEN, [Assoc("G"), Assoc("H")])}
    assert (results["D"].label, results["D"].component_id) == ("replacement", "G-ROOF-B")
    assert (results["F"].label, results["F"].component_id) == ("replacement", "G-ROOF-B")
    assert results["X"].label == "unsure", "contract numbers only link inside one association"


def test_booked_fund_is_not_an_input_only_a_flag():
    on_reserve = _one("roof replacement Bldg A", amount=90_000, fund="reserve")
    on_operating = _one("roof replacement Bldg A", amount=90_000, fund="operating")
    assert (on_reserve.label, on_reserve.component_id) == (on_operating.label, on_operating.component_id)
    assert "booked_to_wrong_fund" not in on_reserve.flags
    assert "booked_to_wrong_fund" in on_operating.flags


def test_domain_code_never_imports_the_generator():
    for path in Path(__file__).resolve().parents[1].joinpath("app", "domain").glob("*.py"):
        tree = ast.parse(path.read_text())
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not [m for m in names if m.startswith("app.synth")], path.name


def _score(seed):
    ds, key = generate(seed)
    results = match_invoices(ds.invoices, ds.components, ds.associations)
    return results, score_matches(results, ds.invoices, {k: asdict(v) for k, v in key.truths.items()})


def test_same_input_same_output():
    ds, _ = generate(4, n_associations=5)
    assert (
        match_invoices(ds.invoices, ds.components, ds.associations)
        == match_invoices(list(reversed(ds.invoices)), list(reversed(ds.components)), ds.associations)[::-1]
    )


@pytest.mark.parametrize(
    ("seed", "floors"),
    [
        (
            7,
            {
                "coverage": 0.88,
                "component_accuracy": 0.86,
                "precision_on_decided": 0.98,
                "dollar_weighted_accuracy": 0.92,
            },
        ),
        (
            11,
            {
                "coverage": 0.86,
                "component_accuracy": 0.85,
                "precision_on_decided": 0.98,
                "dollar_weighted_accuracy": 0.90,
            },
        ),
    ],
)
def test_accuracy_floors(seed, floors):
    _, report = _score(seed)
    for metric, floor in floors.items():
        assert report[metric] >= floor, (seed, metric, report[metric])
    assert report["by_true_type"]["routine"]["accuracy"] >= 0.99
    assert report["wrong_fund_flags"]["recall"] >= 0.84
    assert report["wrong_fund_flags"]["flagged_wrongly"] <= 5


def test_stored_matches_cover_every_invoice_and_rerun_replaces(env, tmp_path):
    from app.db.models import Invoice, InvoiceMatch
    from app.db.session import session_scope
    from app.services.matching import run_rule_matching
    from app.synth.io import load_dataset, write_dataset

    out = tmp_path / "synth"
    write_dataset(*generate(seed=3, n_associations=4), out)
    with session_scope() as db:
        load_dataset(db, out)
    for _ in range(2):
        with session_scope() as db:
            counts = run_rule_matching(db)
    with session_scope() as db:
        n_inv = db.scalar(select(func.count()).select_from(Invoice))
        n_match = db.scalar(select(func.count()).select_from(InvoiceMatch))
        assert n_match == n_inv == sum(v for k, v in counts.items() if k != "flagged_wrong_fund")
        sample = db.scalars(select(InvoiceMatch).where(InvoiceMatch.label != "unsure")).first()
        assert sample.reasons and sample.method == "rules"
    # Reloading the data clears matches along with the invoices they point to.
    with session_scope() as db:
        load_dataset(db, out)
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(InvoiceMatch)) == 0
