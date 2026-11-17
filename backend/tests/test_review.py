"""The capital review queue: sync with reruns, decisions, reviewer matches and the audit log."""

from datetime import date

import pytest
from sqlalchemy import select

from app.core.security import Role, User

MAX = User("max", Role.PROPERTY_MANAGER)


@pytest.fixture()
def boilers(env):
    """One association with two look-alike boilers due in 2019. Bldg A was replaced, but the rules
    matched its invoices to Bldg B, so A looks overdue and B looks replaced. Plus one unsure invoice."""
    from app.db.models import Association, Invoice, InvoiceMatch, Portfolio, ReserveComponent
    from app.db.session import session_scope

    with session_scope() as db:
        db.add(Portfolio(id="P1", name="Test portfolio (synthetic)"))
        db.add(
            Association(
                id="G",
                portfolio_id="P1",
                name="Garden Court",
                kind="garden",
                town="Ardmore",
                units=60,
                buildings=2,
                year_built=1995,
                study_year=2016,
                inflation_rate=0.0,
                reserve_balance_start=100_000,
                annual_contribution=20_000,
            )
        )
        db.flush()
        for b in "AB":
            db.add(
                ReserveComponent(
                    id=f"G-BOIL-{b}",
                    association_id="G",
                    category="mechanical",
                    name="Central boiler plant",
                    location=f"Bldg {b}",
                    useful_life_years=25,
                    remaining_life_years=3,
                    replacement_cost=80_000,
                    planned_year=2019,
                )
            )
        db.flush()
        rows = [
            ("I-START", date(2016, 2, 1), 300.0, "Landscaping", "routine", None),
            ("I-DEP", date(2019, 5, 1), 30_000.0, "Deposit per contract 77 - boiler Bldg A", "replacement", "G-BOIL-B"),
            ("I-FIN", date(2019, 7, 1), 52_000.0, "Balance due - contract 77", "replacement", "G-BOIL-B"),
            ("I-ODD", date(2020, 3, 1), 900.0, "Labor and materials per ticket", "unsure", None),
            ("I-END", date(2025, 11, 1), 300.0, "Landscaping", "routine", None),
        ]
        for inv_id, when, amount, memo, label, _comp in rows:
            db.add(
                Invoice(
                    id=inv_id,
                    association_id="G",
                    vendor_name="Vendor",
                    invoice_number=inv_id,
                    invoice_date=when,
                    amount=amount,
                    memo=memo,
                    fund_booked="reserve" if label == "replacement" else "operating",
                )
            )
        db.flush()
        for inv_id, _, _, _, label, comp in rows:
            db.add(
                InvoiceMatch(
                    invoice_id=inv_id,
                    method="rules",
                    label=label,
                    component_id=comp,
                    confidence=0.9,
                    reasons=[],
                    flags=[],
                )
            )


def _items(db):
    from app.db.models import ReviewItem

    return {i.id: i for i in db.scalars(select(ReviewItem))}


def test_sync_opens_warnings_and_unsure_invoices_and_is_idempotent(boilers):
    from app.db.session import session_scope
    from app.services.review import sync_queue

    with session_scope() as db:
        changes = sync_queue(db)
        assert sorted(changes["opened"]) == ["I:I-ODD", "W:overdue:G-BOIL-A:2019"]
        overdue = _items(db)["W:overdue:G-BOIL-A:2019"]
        assert overdue.status == "open" and overdue.payload["candidate_invoice_ids"] == ["I-DEP", "I-FIN"]
        assert sync_queue(db) == {"opened": [], "reopened": [], "resolved_by_rerun": []}


def test_assigning_the_look_alike_invoices_clears_the_false_overdue_and_logs_the_change(boilers):
    from app.db.models import InvoiceMatch, ReviewAction
    from app.db.session import session_scope
    from app.services.review import assign, sync_queue

    with session_scope() as db:
        sync_queue(db)
        assign(db, "I-DEP", "G-BOIL-A", "contract 77 is Bldg A", MAX)
        item, changes = assign(db, "I-FIN", "G-BOIL-A", None, MAX)
        assert "W:overdue:G-BOIL-A:2019" in changes["resolved_by_rerun"]
        assert "W:overdue:G-BOIL-B:2019" in changes["opened"], "B was never replaced: now it is overdue"
        assert item.status == "resolved"
        fin = db.get(InvoiceMatch, ("I-FIN", "reviewer"))
        assert (fin.label, fin.component_id) == ("replacement", "G-BOIL-A"), "code applies the 15% rule"
        log = db.scalars(select(ReviewAction).where(ReviewAction.item_id == "I:I-FIN")).all()
        assign_row = next(r for r in log if r.action == "assign")
        assert assign_row.match_before["component_id"] == "G-BOIL-B"
        assert assign_row.match_after["component_id"] == "G-BOIL-A"
        assert (assign_row.username, assign_row.role) == ("max", "property_manager")
        system = db.scalars(select(ReviewAction).where(ReviewAction.item_id == "W:overdue:G-BOIL-A:2019")).all()
        assert [r.status_after for r in system] == ["open", "resolved_by_rerun"]
        assert {r.username for r in system} == {"system"}


def test_a_dismissal_survives_reruns_and_a_cleared_item_reopens(boilers):
    from app.db.session import session_scope
    from app.services.review import assign, decide, sync_queue

    key = "W:overdue:G-BOIL-A:2019"
    with session_scope() as db:
        sync_queue(db)
        decide(db, key, "dismiss", "board knows; replacement is booked for spring", MAX)
        assign(db, "I-DEP", "G-BOIL-A", None, MAX)
        assign(db, "I-FIN", "G-BOIL-A", None, MAX)
        assert _items(db)[key].status == "dismissed", "a rerun never changes a person's decision"


def test_an_item_cleared_by_a_rerun_reopens_when_the_warning_returns(boilers):
    from app.db.session import session_scope
    from app.services.review import assign, sync_queue

    key = "W:overdue:G-BOIL-A:2019"
    with session_scope() as db:
        sync_queue(db)
        assign(db, "I-DEP", "G-BOIL-A", None, MAX)
        _, cleared = assign(db, "I-FIN", "G-BOIL-A", None, MAX)
        assert key in cleared["resolved_by_rerun"]
        _, back = assign(db, "I-FIN", "G-BOIL-B", "wrong call, it was B", MAX)
        assert key in back["reopened"], "a deposit alone isn't a finished replacement"
        assert _items(db)[key].status == "open"


def test_decisions_are_validated(boilers):
    from app.db.session import session_scope
    from app.services.review import ReviewError, assign, decide, sync_queue

    with session_scope() as db:
        sync_queue(db)
        with pytest.raises(ReviewError, match="needs a comment"):
            decide(db, "W:overdue:G-BOIL-A:2019", "dismiss", "  ", MAX)
        with pytest.raises(ReviewError, match="for warnings"):
            decide(db, "I:I-ODD", "confirm", None, MAX)
        with pytest.raises(ReviewError, match="unknown action"):
            decide(db, "I:I-ODD", "approve", None, MAX)
        with pytest.raises(ReviewError, match="not a component of G"):
            assign(db, "I-ODD", "Z-ROOF", None, MAX)
        with pytest.raises(LookupError):
            decide(db, "W:nope", "confirm", None, MAX)


def test_reviews_do_not_change_the_combined_method(boilers):
    from app.db.session import session_scope
    from app.services.llm_matching import combined_matches, reviewed_matches
    from app.services.review import assign, sync_queue

    with session_scope() as db:
        sync_queue(db)
        assign(db, "I-ODD", None, None, MAX)
        combined = {m.invoice_id: m.label for m in combined_matches(db)}
        reviewed = {m.invoice_id: m.label for m in reviewed_matches(db)}
    assert combined["I-ODD"] == "unsure" and reviewed["I-ODD"] == "routine"


BOARD = {"Authorization": "Bearer board-token"}
MANAGER = {"Authorization": "Bearer manager-token"}
ADMIN = {"Authorization": "Bearer admin-token"}
ANALYST = {"Authorization": "Bearer analyst-token"}


@pytest.fixture()
def api(boilers):
    from fastapi.testclient import TestClient

    from app.db.session import session_scope
    from app.main import create_app
    from app.services.review import sync_queue

    with session_scope() as db:
        sync_queue(db)
    with TestClient(create_app()) as c:
        yield c


def test_board_members_read_but_cannot_decide(api):
    page = api.get("/api/capital/queue", headers=BOARD).json()
    assert [i["id"] for i in page["items"]] == ["W:overdue:G-BOIL-A:2019", "I:I-ODD"], "warnings first"
    detail = api.get("/api/capital/queue/W:overdue:G-BOIL-A:2019", headers=BOARD).json()
    assert [(i["id"], i["role"], i["component_id"]) for i in detail["invoices"]] == [
        ("I-DEP", "candidate", "G-BOIL-B"),
        ("I-FIN", "candidate", "G-BOIL-B"),
    ]
    decision = {"action": "confirm"}
    assert (
        api.post("/api/capital/queue/W:overdue:G-BOIL-A:2019/decisions", json=decision, headers=BOARD).status_code
        == 403
    )
    assert (
        api.post("/api/capital/invoices/I-ODD/assignment", json={"component_id": None}, headers=BOARD).status_code
        == 403
    )
    assert api.post("/api/capital/queue/sync", headers=BOARD).status_code == 403
    assert api.get("/api/capital/queue", headers=ANALYST).status_code == 403, "Tick & Tie roles don't see it"
    assert api.get("/api/capital/queue").status_code == 401


def test_property_managers_decide_and_every_decision_is_logged(api):
    url = "/api/capital/queue/W:overdue:G-BOIL-A:2019/decisions"
    assert api.post(url, json={"action": "dismiss"}, headers=MANAGER).status_code == 422
    r = api.post(url, json={"action": "confirm", "comment": "boiler is 40 years old"}, headers=MANAGER)
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    actions = r.json()["actions"]
    assert [(a["action"], a["username"], a["status_after"]) for a in actions] == [
        ("rerun", "system", "open"),
        ("confirm", "max", "confirmed"),
    ]
    assert (
        api.post("/api/capital/queue/W:nope/decisions", json={"action": "confirm"}, headers=MANAGER).status_code == 404
    )


def test_assignment_over_the_api_reports_what_the_rerun_changed(api):
    body = {"component_id": "G-BOIL-A", "comment": "contract 77 is Bldg A"}
    api.post("/api/capital/invoices/I-DEP/assignment", json=body, headers=MANAGER)
    r = api.post("/api/capital/invoices/I-FIN/assignment", json=body, headers=MANAGER)
    assert r.status_code == 200
    assert r.json()["changes"]["resolved_by_rerun"] == ["W:overdue:G-BOIL-A:2019"]
    assert r.json()["changes"]["opened"] == ["W:overdue:G-BOIL-B:2019"]
    bad = api.post("/api/capital/invoices/I-ODD/assignment", json={"component_id": "X-1"}, headers=MANAGER)
    assert bad.status_code == 422
    assert (
        api.post("/api/capital/invoices/NOPE/assignment", json={"component_id": None}, headers=MANAGER).status_code
        == 404
    )
    assert api.post("/api/capital/queue/sync", headers=MANAGER).status_code == 403
    assert api.post("/api/capital/queue/sync", headers=ADMIN).json() == {
        "opened": [],
        "reopened": [],
        "resolved_by_rerun": [],
    }
    parts = api.get("/api/capital/components", params={"association_id": "G"}, headers=BOARD).json()
    assert [p["id"] for p in parts] == ["G-BOIL-A", "G-BOIL-B"]
