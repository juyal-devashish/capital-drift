"""Run the rule matcher over the database and store its decisions in invoice_matches."""

from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Association, Invoice, InvoiceMatch, ReserveComponent
from app.domain.matching import match_invoices


def run_rule_matching(db: Session) -> dict[str, int]:
    """Match every invoice with the rules, replacing earlier rule matches. Returns counts by label."""
    invoices = list(db.scalars(select(Invoice).order_by(Invoice.id)))
    components = list(db.scalars(select(ReserveComponent)))
    associations = list(db.scalars(select(Association)))
    results = match_invoices(invoices, components, associations)
    db.execute(delete(InvoiceMatch).where(InvoiceMatch.method == "rules"))
    db.add_all(
        InvoiceMatch(
            invoice_id=r.invoice_id,
            label=r.label,
            component_id=r.component_id,
            confidence=r.confidence,
            method=r.method,
            reasons=r.reasons,
            flags=r.flags,
        )
        for r in results
    )
    db.flush()
    counts = Counter(r.label for r in results)
    counts["flagged_wrong_fund"] = sum("booked_to_wrong_fund" in r.flags for r in results)
    return dict(sorted(counts.items()))
