"""Board status rule, plan schedule, year-by-year view, and the board/timeline/results endpoints."""

from dataclasses import dataclass
from datetime import date

import pytest

from app.domain.capital_view import QueueEntry, association_status, plan_schedule, year_by_year
from app.domain.matching import MatchResult


def _w(kind, status, title="Roof: x", amount=10_000.0, by=None):
    return QueueEntry("warning", kind, status, title, amount, by)


def _inv(status, amount):
    return QueueEntry("invoice", None, status, "Vendor: memo", amount)


def test_red_needs_a_failing_or_overdue_warning_that_is_open_or_confirmed():
    s = association_status([_w("overdue", "open", "Boiler: past its 2020 replacement")], 50_000)
    assert s.status == "red" and s.reasons == ["Boiler: past its 2020 replacement (not yet checked by the manager)"]
    s = association_status([_w("failing_early", "confirmed", "Siding: failing early", by="max")], 50_000)
    assert s.status == "red" and s.reasons == ["Siding: failing early (confirmed by max)"]
    for status in ("dismissed", "resolved_by_rerun"):
        assert association_status([_w("overdue", status)], 50_000).status == "green", status


def test_amber_is_over_budget_or_enough_unplaced_money():
    assert association_status([_w("over_budget", "open")], 50_000).status == "amber"
    assert association_status([_inv("open", 4_000), _inv("open", 1_000)], 50_000).status == "amber"
    quiet = association_status([_inv("open", 4_000), _inv("resolved", 9_000)], 50_000)
    assert quiet.status == "green" and quiet.unplaced_invoices == 1
    assert quiet.reasons == ["1 invoice worth $4,000 not yet placed against a part of the plan"]
    assert association_status([], 50_000).status == "green"


@dataclass
class Comp:
    id: str
    association_id: str = "G"
    name: str = "Sealcoat"
    location: str | None = None
    useful_life_years: int = 4
    remaining_life_years: int = 1
    replacement_cost: float = 10_000.0
    planned_year: int = 2017


@dataclass
class Assoc:
    id: str = "G"
    study_year: int = 2016
    inflation_rate: float = 0.03


@dataclass
class Inv:
    id: str
    invoice_date: date
    amount: float
    association_id: str = "G"


def test_plan_schedule_repeats_every_useful_life_inflated():
    assert plan_schedule(Comp("S"), Assoc(), 2016, 2025) == [(2017, 10_300.0), (2021, 11_592.74), (2025, 13_047.73)]


def test_year_by_year_splits_spend_by_how_it_was_matched():
    invoices = [
        Inv("R", date(2017, 6, 1), 10_000),
        Inv("P", date(2019, 3, 1), 500),
        Inv("U", date(2019, 4, 1), 700),
        Inv("O", date(2019, 5, 1), 90, association_id="OTHER"),
    ]
    matches = [
        MatchResult("R", "replacement", "S", 1.0, []),
        MatchResult("P", "repair", "S", 1.0, []),
        MatchResult("U", "unsure", None, 0.0, []),
    ]
    view = year_by_year([Comp("S")], Assoc(), invoices, matches, 2016, 2025)
    by_year = {r["year"]: r for r in view["years"]}
    assert (by_year[2017]["planned"], by_year[2017]["replacements"]) == (10_300.0, 10_000.0)
    assert (by_year[2019]["repairs"], by_year[2019]["unplaced"]) == (500.0, 700.0)
    assert view["parts"][0]["planned_years"] == [2017, 2021, 2025]
    assert view["parts"][0]["replacement_spend_by_year"] == {"2017": 10_000.0}


def test_board_timeline_and_results_endpoints(boilers, tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app

    board_hdr = {"Authorization": "Bearer board-token"}
    unknown = {"Authorization": "Bearer not-a-token"}
    results = tmp_path / "results.json"
    monkeypatch.setattr(get_settings(), "capital_results_file", results)
    with TestClient(create_app()) as c:
        before = c.get("/api/capital/board", headers=board_hdr).json()
        assert before["synced"] is False and before["associations"][0]["status"] == "green"
        c.post("/api/capital/queue/sync", headers={"Authorization": "Bearer admin-token"})
        after = c.get("/api/capital/board", headers=board_hdr).json()
        assert after["synced"] is True and "Red:" in after["rule"]
        g = after["associations"][0]
        assert g["status"] == "red" and g["reasons"][0].startswith("Central boiler plant (Bldg A): past its 2019")
        t = c.get("/api/capital/associations/G", headers=board_hdr).json()
        assert t["status"]["status"] == "red" and [w["id"] for w in t["warnings"]] == ["W:overdue:G-BOIL-A:2019"]
        assert next(r for r in t["years"] if r["year"] == 2019)["replacements"] == 82_000.0
        assert c.get("/api/capital/associations/NOPE", headers=board_hdr).status_code == 404
        assert c.get("/api/capital/board", headers=unknown).status_code == 401
        fc = c.get("/api/capital/forecast", headers=board_hdr).json()
        assert fc["as_of"] == 2025 and [r["association_id"] for r in fc["associations"]] == ["G"]
        assert "modelled shortfall" in fc["assumptions"]
        assert t["forecast"]["as_of"] == 2025 and t["forecast_rising"]["history"][-1]["contributions"] == 20_000, (
            "0% inflation: rising = flat"
        )
        assert c.get("/api/capital/forecast", headers=unknown).status_code == 401
        assert c.get("/api/capital/results", headers=board_hdr).status_code == 404
        results.write_text(json.dumps({"label": "SYNTHETIC"}))
        assert c.get("/api/capital/results", headers=board_hdr).json() == {"label": "SYNTHETIC"}


def test_export_static_writes_what_a_board_member_sees(boilers, tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from app.cli import cmd_export_static
    from app.core.config import get_settings
    from app.db.session import session_scope
    from app.services.review import sync_queue

    results = tmp_path / "results.json"
    results.write_text(json.dumps({"label": "SYNTHETIC"}))
    monkeypatch.setattr(get_settings(), "capital_results_file", results)
    with session_scope() as db:
        sync_queue(db)
    out = tmp_path / "demo"
    cmd_export_static(SimpleNamespace(out=str(out), token="board-token"))
    queue = json.loads((out / "queue.json").read_text())
    items = json.loads((out / "items" / "G.json").read_text())
    assert sorted(items) == sorted(i["id"] for i in queue["items"]) == ["I:I-ODD", "W:overdue:G-BOIL-A:2019"]
    assert json.loads((out / "associations" / "G.json").read_text())["status"]["status"] == "red"
    assert json.loads((out / "results.json").read_text()) == {"label": "SYNTHETIC"}
    assert not any(":" in p.name for p in out.rglob("*")), "file names must work on every file system"
    with pytest.raises(SystemExit, match="board member"):
        cmd_export_static(SimpleNamespace(out=str(out), token="manager-token"))
