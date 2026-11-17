"""
Test configuration: every test gets its own temporary data directory (SQLite database), and cached
singletons are reset so nothing leaks between tests.
"""

import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Point the app at a fresh temp data dir and reset all cached singletons."""
    monkeypatch.setenv("CD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CD_LOG_LEVEL", "WARNING")
    from app.core.config import get_settings
    from app.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()
    from app.db.migrate import upgrade

    upgrade()
    yield tmp_path
    reset_engine()
    get_settings.cache_clear()


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


def pytest_configure():
    os.environ.setdefault("CD_LOG_LEVEL", "WARNING")
