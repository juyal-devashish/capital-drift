"""Watch every component's matched spend against its plan, and store the warnings."""

from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Association, Invoice, ReserveComponent, SpendWarningRecord
from app.domain.warnings import SpendWarning, spend_from_matches, watch_spend, watch_window
from app.services.llm_matching import combined_matches, stored_matches


def run_warnings(db: Session, method: str = "combined") -> dict:
    """Replay the history with ``method``'s matches (rules or combined), replacing that method's warnings."""
    matches = combined_matches(db) if method == "combined" else stored_matches(db, method)
    invoices = list(db.scalars(select(Invoice)))
    if not invoices:
        raise RuntimeError("no invoices loaded; run `synth` first")
    if len(matches) != len(invoices):
        raise RuntimeError(f"{len(matches)} {method} matches for {len(invoices)} invoices; run `match` first")
    start, through = watch_window(invoices)
    warnings = watch_spend(
        list(db.scalars(select(ReserveComponent))),
        list(db.scalars(select(Association))),
        spend_from_matches(matches, invoices),
        start,
        through,
    )
    db.execute(delete(SpendWarningRecord).where(SpendWarningRecord.method == method))
    db.add_all(_record(w, method) for w in warnings)
    db.flush()
    return {
        "method": method,
        "window": [start.isoformat(), through.isoformat()],
        "warnings": len(warnings),
        "by_kind": dict(sorted(Counter(w.kind for w in warnings).items())),
    }


def stored_warnings(db: Session, method: str) -> list[SpendWarning]:
    rows = db.scalars(
        select(SpendWarningRecord).where(SpendWarningRecord.method == method).order_by(SpendWarningRecord.id)
    )
    return [
        SpendWarning(
            r.kind, r.association_id, r.component_id, r.fired_on, r.headline, r.message, r.numbers, r.invoice_ids
        )
        for r in rows
    ]


def _record(w: SpendWarning, method: str) -> SpendWarningRecord:
    return SpendWarningRecord(
        method=method,
        kind=w.kind,
        association_id=w.association_id,
        component_id=w.component_id,
        fired_on=w.fired_on,
        headline=w.headline,
        message=w.message,
        numbers=w.numbers,
        invoice_ids=w.invoice_ids,
    )
