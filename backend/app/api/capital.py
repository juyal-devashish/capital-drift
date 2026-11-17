"""Capital planning review queue: warnings and unsure invoices, decisions and invoice assignments.

Board members read. Property managers and admins decide. Only admins trigger a full rerun.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import CAPITAL_ADMIN_ROLES, CAPITAL_DECIDE_ROLES, CAPITAL_READ_ROLES, User, require_roles
from app.db.models import Association, Invoice, ReserveComponent, ReviewAction, ReviewItem
from app.db.session import get_db
from app.domain.capital_view import STATUS_RULE, QueueEntry, association_status, year_by_year
from app.schemas import (
    AssignmentIn,
    AssignmentOut,
    AssociationTimeline,
    BoardAssociation,
    BoardOut,
    ComponentOut,
    ForecastBoard,
    ForecastOut,
    ForecastRow,
    QueueChanges,
    RelatedInvoice,
    ReviewDecisionIn,
    ReviewItemDetail,
    ReviewItemOut,
    ReviewItemPage,
)
from app.services import review
from app.services.forecast import ASSUMPTIONS, forecast_both
from app.services.llm_matching import reviewed_matches

router = APIRouter(prefix="/capital", tags=["capital"])

_STATUS_ORDER = {"open": 0, "confirmed": 1, "dismissed": 2, "resolved": 3, "resolved_by_rerun": 4}


@router.get("/queue", response_model=ReviewItemPage)
def list_queue(
    status_: str | None = Query("open", alias="status", description="comma-separated; empty for all"),
    kind: str | None = Query(None, description="warning | invoice"),
    association_id: str | None = None,
    warning_kind: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*CAPITAL_READ_ROLES)),
):
    """Warnings before invoices, then the most money at stake first."""
    stmt = select(ReviewItem)
    if status_:
        stmt = stmt.where(ReviewItem.status.in_(status_.split(",")))
    if kind:
        stmt = stmt.where(ReviewItem.kind == kind)
    if association_id:
        stmt = stmt.where(ReviewItem.association_id == association_id)
    if warning_kind:
        stmt = stmt.where(ReviewItem.warning_kind == warning_kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = (
        case(_STATUS_ORDER, value=ReviewItem.status, else_=9),
        case({"warning": 0}, value=ReviewItem.kind, else_=1),
        # Past-due warnings first: their candidate invoices clear most false alarms (docs/results.md).
        case({"overdue": 0, "over_budget": 1, "failing_early": 2}, value=ReviewItem.warning_kind, else_=3),
        ReviewItem.amount_at_stake.desc(),
        ReviewItem.id,
    )
    items = db.scalars(stmt.order_by(*order).limit(limit).offset(offset)).all()
    return ReviewItemPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/queue/{item_id}", response_model=ReviewItemDetail)
def get_item(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_roles(*CAPITAL_READ_ROLES))):
    item = db.get(ReviewItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review item not found")
    roles = {i: "evidence" for i in item.payload.get("invoice_ids", [])}
    roles.update({i: "candidate" for i in item.payload.get("candidate_invoice_ids", [])})
    if item.invoice_id:
        roles[item.invoice_id] = "evidence"
    matches = {m.invoice_id: m for m in reviewed_matches(db)} if roles else {}
    invoices = []
    for inv_id, role in roles.items():
        inv, m = db.get(Invoice, inv_id), matches.get(inv_id)
        if inv is None or m is None:
            continue
        invoices.append(
            RelatedInvoice(
                id=inv.id,
                invoice_date=inv.invoice_date,
                vendor_name=inv.vendor_name,
                memo=inv.memo,
                amount=inv.amount,
                fund_booked=inv.fund_booked,
                label=m.label,
                component_id=m.component_id,
                method=m.method,
                role=role,
            )
        )
    invoices.sort(key=lambda r: (r.invoice_date, r.id))
    actions = db.scalars(select(ReviewAction).where(ReviewAction.item_id == item.id).order_by(ReviewAction.id)).all()
    return ReviewItemDetail(
        **ReviewItemOut.model_validate(item).model_dump(), payload=item.payload, invoices=invoices, actions=actions
    )


@router.post("/queue/{item_id}/decisions", response_model=ReviewItemDetail)
def decide(
    item_id: str,
    body: ReviewDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*CAPITAL_DECIDE_ROLES)),
):
    """Confirm or dismiss a warning, reopen an item, or add a comment. Every action is logged."""
    try:
        review.decide(db, item_id, body.action, body.comment, user)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review item not found") from None
    except review.ReviewError as e:
        raise HTTPException(422, str(e)) from None
    return get_item(item_id, db)


@router.post("/invoices/{invoice_id}/assignment", response_model=AssignmentOut)
def assign_invoice(
    invoice_id: str,
    body: AssignmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*CAPITAL_DECIDE_ROLES)),
):
    """Say which part an invoice was for (or routine). Reruns warnings and returns what changed."""
    try:
        item, changes = review.assign(db, invoice_id, body.component_id, body.comment, user)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found") from None
    except review.ReviewError as e:
        raise HTTPException(422, str(e)) from None
    return AssignmentOut(item=ReviewItemOut.model_validate(item), changes=QueueChanges(**changes))


@router.post("/queue/sync", response_model=QueueChanges)
def sync(db: Session = Depends(get_db), _: User = Depends(require_roles(*CAPITAL_ADMIN_ROLES))):
    """Rerun the warnings on the reviewed matches and reconcile the queue."""
    return QueueChanges(**review.sync_queue(db))


@router.get("/components", response_model=list[ComponentOut])
def components(
    association_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*CAPITAL_READ_ROLES)),
):
    """The reserve study's parts for one association, for the assignment picker."""
    return db.scalars(
        select(ReserveComponent).where(ReserveComponent.association_id == association_id).order_by(ReserveComponent.id)
    ).all()


def _statuses(db: Session) -> dict[str, BoardAssociation]:
    confirmed_by = {
        a.item_id: a.username
        for a in db.scalars(select(ReviewAction).where(ReviewAction.action == "confirm").order_by(ReviewAction.id))
    }
    entries: dict[str, list[QueueEntry]] = {}
    for i in db.scalars(select(ReviewItem)):
        entries.setdefault(i.association_id, []).append(
            QueueEntry(i.kind, i.warning_kind, i.status, i.title, i.amount_at_stake, confirmed_by.get(i.id))
        )
    out = {}
    for a in db.scalars(select(Association).order_by(Association.id)):
        s = association_status(entries.get(a.id, []), a.annual_contribution)
        out[a.id] = BoardAssociation(id=a.id, name=a.name, kind=a.kind, town=a.town, units=a.units, **s.__dict__)
    return out


@router.get("/board", response_model=BoardOut)
def board(db: Session = Depends(get_db), _: User = Depends(require_roles(*CAPITAL_READ_ROLES))):
    """Every association, red first, with the reasons in plain words."""
    rank = {"red": 0, "amber": 1, "green": 2}
    rows = sorted(_statuses(db).values(), key=lambda r: (rank[r.status], -r.open_warnings - r.confirmed_warnings, r.id))
    synced = db.scalar(select(func.count()).select_from(ReviewItem)) > 0
    return BoardOut(synced=synced, rule=STATUS_RULE, associations=rows)


@router.get("/associations/{association_id}", response_model=AssociationTimeline)
def association(
    association_id: str, db: Session = Depends(get_db), _: User = Depends(require_roles(*CAPITAL_READ_ROLES))
):
    """Plan against actual year by year (reviewed matches), the parts, and this association's warnings."""
    a = db.get(Association, association_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Association not found")
    invoices = list(db.scalars(select(Invoice).where(Invoice.association_id == a.id)))
    components = list(db.scalars(select(ReserveComponent).where(ReserveComponent.association_id == a.id)))
    all_years = [i.invoice_date.year for i in db.scalars(select(Invoice))]
    first, last = (min(all_years), max(all_years)) if all_years else (a.study_year, a.study_year)
    view = year_by_year(components, a, invoices, reviewed_matches(db), first, last)
    both = forecast_both(db)
    warnings = db.scalars(
        select(ReviewItem)
        .where(ReviewItem.association_id == a.id, ReviewItem.kind == "warning")
        .order_by(ReviewItem.opened_on)
    ).all()
    return AssociationTimeline(
        id=a.id,
        name=a.name,
        kind=a.kind,
        town=a.town,
        units=a.units,
        buildings=a.buildings,
        study_year=a.study_year,
        inflation_rate=a.inflation_rate,
        annual_contribution=a.annual_contribution,
        reserve_balance_start=a.reserve_balance_start,
        status=_statuses(db)[a.id],
        years=view["years"],
        parts=view["parts"],
        warnings=warnings,
        **{
            key: next((ForecastOut(**f.__dict__) for f in fs if f.association_id == a.id), None)
            for key, fs in (("forecast", both["flat"]), ("forecast_rising", both["rising"]))
        },
        forecast_assumptions=ASSUMPTIONS,
    )


@router.get("/forecast", response_model=ForecastBoard)
def forecast(db: Session = Depends(get_db), _: User = Depends(require_roles(*CAPITAL_READ_ROLES))):
    """Which associations run short of reserve money first: most likely first, then soonest."""
    statuses = _statuses(db)
    names = {a.id: a for a in db.scalars(select(Association))}
    both = forecast_both(db)
    forecasts, rising = both["flat"], {f.association_id: f for f in both["rising"]}
    rows = []
    for f in forecasts:
        a, r = names[f.association_id], rising[f.association_id]
        rows.append(
            ForecastRow(
                association_id=f.association_id,
                name=a.name,
                status=statuses[f.association_id].status,
                start_balance=f.start_balance,
                annual_contribution=a.annual_contribution,
                share_short=f.share_short,
                first_short_year=f.first_short_year,
                lowest_p50_in_contributions=round(min(y["p50"] for y in f.years) / a.annual_contribution, 2),
                start_balance_rising=r.start_balance,
                share_short_rising=r.share_short,
                first_short_year_rising=r.first_short_year,
            )
        )
    # Already short first, deepest (in years of contributions) first; then most likely to run short,
    # then soonest, then deepest.
    rows.sort(
        key=lambda r: (
            r.start_balance >= 0,
            r.start_balance / r.annual_contribution if r.start_balance < 0 else 0,
            -r.share_short,
            r.first_short_year or 9999,
            r.lowest_p50_in_contributions,
        )
    )
    as_of = forecasts[0].as_of if forecasts else None
    return ForecastBoard(as_of=as_of, assumptions=ASSUMPTIONS, associations=rows)


@router.get("/results")
def results(_: User = Depends(require_roles(*CAPITAL_READ_ROLES))) -> dict:
    """Offline evaluation results (synthetic data), written by `app.cli results`. The app never scores live."""
    path = get_settings().capital_results_file
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No results file yet; run `python -m app.cli results`")
    return json.loads(path.read_text(encoding="utf-8"))
