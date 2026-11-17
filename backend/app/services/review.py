"""
The capital review queue: warnings and unsure invoices for property managers to decide.

* ``sync_queue`` reruns the warnings on the reviewed matches (a property manager's answer, else
  Claude's, else the rules') and reconciles the queue. New warnings and unsure invoices open items.
  An open item that no longer applies becomes ``resolved_by_rerun``; one that comes back reopens.
  Items a person decided (confirmed, dismissed, resolved) are never changed by a rerun.
* ``decide`` records confirm, dismiss, reopen or comment on an item.
* ``assign`` records a property manager's answer for one invoice (a component, or routine). Code
  applies the 15% repair/replacement rule and the wrong-fund flag, as it does for Claude. Any
  invoice can be corrected, not only unsure ones: a replacement matched to the look-alike part in
  another building is a common cause of false overdue warnings.

Every change is appended to ``review_actions``, automatic ones as user ``system``.
"""

from dataclasses import asdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import User
from app.db.models import Association, Invoice, InvoiceMatch, ReserveComponent, ReviewAction, ReviewItem
from app.domain.matching import MatchResult, fund_flag, with_work_type
from app.domain.warnings import SpendWarning, overdue_candidates
from app.services.llm_matching import reviewed_matches
from app.services.warnings import run_warnings, stored_warnings

OPEN, CONFIRMED, DISMISSED, RESOLVED, RERUN = "open", "confirmed", "dismissed", "resolved", "resolved_by_rerun"
DECIDED = (CONFIRMED, DISMISSED, RESOLVED)
_ACTIONS = {"confirm": CONFIRMED, "dismiss": DISMISSED, "reopen": OPEN, "comment": None}
SYSTEM = ("system", "system")


class ReviewError(ValueError):
    """A request the queue refuses (bad action, missing comment, component from another association)."""


def warning_key(w: SpendWarning) -> str:
    """Stable across reruns: the part and the plan cycle, not the firing date (which can move)."""
    cycle = w.numbers["project_start"][:4] if w.kind == "over_budget" else w.numbers["planned_year"]
    return f"W:{w.kind}:{w.component_id}:{cycle}"


def invoice_key(invoice_id: str) -> str:
    return f"I:{invoice_id}"


def _log(db: Session, item: ReviewItem, action: str, who: tuple[str, str], before: str | None, **extra) -> None:
    db.add(
        ReviewAction(
            item_id=item.id,
            action=action,
            status_before=before,
            status_after=item.status,
            username=who[0],
            role=who[1],
            **extra,
        )
    )


def sync_queue(db: Session) -> dict:
    """Rerun warnings on the reviewed matches and reconcile the queue. Returns what changed."""
    run_warnings(db, "reviewed")
    warnings = stored_warnings(db, "reviewed")
    matches = reviewed_matches(db)
    invoices = list(db.scalars(select(Invoice)))
    components = list(db.scalars(select(ReserveComponent)))
    associations = list(db.scalars(select(Association)))
    by_inv = {i.id: i for i in invoices}

    current: dict[str, dict] = {}
    for w in warnings:
        payload = {"message": w.message, "numbers": w.numbers, "invoice_ids": w.invoice_ids}
        if w.kind == "overdue":
            payload["candidate_invoice_ids"] = overdue_candidates(w, components, associations, invoices, matches)
        current[warning_key(w)] = {
            "kind": "warning",
            "warning_kind": w.kind,
            "association_id": w.association_id,
            "component_id": w.component_id,
            "invoice_id": None,
            "title": w.headline,
            "detail": w.message,
            "amount_at_stake": w.numbers.get("project_total") or w.numbers.get("plan_cost") or 0.0,
            "opened_on": w.fired_on,
            "payload": payload,
        }
    for m in matches:
        if m.label != "unsure":
            continue
        inv = by_inv[m.invoice_id]
        current[invoice_key(inv.id)] = {
            "kind": "invoice",
            "warning_kind": None,
            "association_id": inv.association_id,
            "component_id": None,
            "invoice_id": inv.id,
            "title": f"{inv.vendor_name}: {inv.memo}"[:200],
            "detail": f"Neither the rules nor Claude could place this ${inv.amount:,.0f} invoice. "
            "Pick the part it was for, or mark it routine upkeep.",
            "amount_at_stake": inv.amount,
            "opened_on": inv.invoice_date,
            "payload": {"reasons": m.reasons},
        }

    existing = {i.id: i for i in db.scalars(select(ReviewItem))}
    changes: dict[str, list[str]] = {"opened": [], "reopened": [], "resolved_by_rerun": []}
    for key, fields in current.items():
        item = existing.get(key)
        if item is None:
            item = ReviewItem(id=key, status=OPEN, **fields)
            db.add(item)
            db.flush()
            _log(db, item, "rerun", SYSTEM, None, comment="raised by a rerun")
            changes["opened"].append(key)
            continue
        for name, value in fields.items():
            setattr(item, name, value)
        if item.status == RERUN:
            item.status = OPEN
            _log(db, item, "rerun", SYSTEM, RERUN, comment="raised again by a rerun")
            changes["reopened"].append(key)
    for key, item in existing.items():
        if key not in current and item.status == OPEN:
            item.status = RERUN
            _log(db, item, "rerun", SYSTEM, OPEN, comment="no longer raised after a rerun")
            changes["resolved_by_rerun"].append(key)
    db.flush()
    return changes


def decide(db: Session, item_id: str, action: str, comment: str | None, user: User) -> ReviewItem:
    """Confirm, dismiss, reopen or comment on a queue item. Dismissing or commenting needs a comment."""
    item = db.get(ReviewItem, item_id, with_for_update=True)
    if item is None:
        raise LookupError(item_id)
    if action not in _ACTIONS:
        raise ReviewError(f"unknown action {action!r}")
    if action in ("dismiss", "comment") and not (comment or "").strip():
        raise ReviewError(f"'{action}' needs a comment saying why")
    if action in ("confirm", "dismiss", "reopen") and item.kind != "warning":
        raise ReviewError(f"'{action}' is for warnings; to change an invoice, assign it again")
    before = item.status
    if _ACTIONS[action]:
        item.status = _ACTIONS[action]
    _log(db, item, action, (user.username, str(user.role)), before, comment=comment)
    db.flush()
    return item


def _match_dict(m: MatchResult | None) -> dict | None:
    return None if m is None else {k: v for k, v in asdict(m).items() if k != "reasons"}


def assign(
    db: Session, invoice_id: str, component_id: str | None, comment: str | None, user: User
) -> tuple[ReviewItem, dict]:
    """Record a property manager's answer for an invoice (``component_id`` None means routine upkeep).

    Then rerun warnings and reconcile the queue; returns the invoice's item and what changed.
    """
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise LookupError(invoice_id)
    assoc = db.get(Association, inv.association_id)
    if component_id is None:
        result = MatchResult(inv.id, "routine", None, 1.0, [f"reviewer {user.username}: routine upkeep"])
    else:
        comp = db.get(ReserveComponent, component_id)
        if comp is None or comp.association_id != inv.association_id:
            raise ReviewError(f"{component_id} is not a component of {inv.association_id}")
        result = with_work_type(inv, comp, assoc, 1.0, [f"reviewer {user.username}"])
    result.method = "reviewer"
    fund_flag(result, inv)

    before = next((m for m in reviewed_matches(db) if m.invoice_id == inv.id), None)
    db.execute(delete(InvoiceMatch).where(InvoiceMatch.invoice_id == inv.id, InvoiceMatch.method == "reviewer"))
    db.add(
        InvoiceMatch(
            invoice_id=inv.id,
            method="reviewer",
            label=result.label,
            component_id=result.component_id,
            confidence=result.confidence,
            reasons=result.reasons,
            flags=result.flags,
        )
    )
    key = invoice_key(inv.id)
    item = db.get(ReviewItem, key)
    if item is None:  # correcting a decided match: give it an item so the log has somewhere to live
        item = ReviewItem(
            id=key,
            kind="invoice",
            association_id=inv.association_id,
            invoice_id=inv.id,
            title=f"{inv.vendor_name}: {inv.memo}"[:200],
            detail="Corrected by a property manager.",
            amount_at_stake=inv.amount,
            opened_on=inv.invoice_date,
            status=RESOLVED,
            payload={},
        )
        db.add(item)
        status_before = None
    else:
        status_before = item.status
        item.status = RESOLVED
    db.flush()
    _log(
        db,
        item,
        "assign",
        (user.username, str(user.role)),
        status_before,
        comment=comment,
        match_before=_match_dict(before),
        match_after=_match_dict(result),
    )
    db.flush()
    return item, sync_queue(db)


def queue_counts(db: Session) -> dict:
    rows = db.scalars(select(ReviewItem)).all()
    out: dict[str, int] = {}
    for r in rows:
        out[f"{r.kind}:{r.status}"] = out.get(f"{r.kind}:{r.status}", 0) + 1
    return dict(sorted(out.items()))
