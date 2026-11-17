"""Forecast every association's reserve balance from the reviewed matches and the open warnings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Association, Invoice, ReserveComponent, ReviewItem
from app.domain.forecast import Forecast, ForecastSettings, completed_projects, cost_ratios, forecast_association
from app.domain.warnings import spend_from_matches
from app.services.llm_matching import reviewed_matches

ASSUMPTIONS = (
    "Contributions were paid in full, either flat at the study's recommended figure or rising with the "
    "study's inflation rate (the study doesn't say which, so both are shown); the reserve earns no interest. "
    "A balance below zero is a modelled shortfall: work that would need other money, or would be put off. "
    "Planned replacements happen when due, at the plan's inflated cost times a ratio drawn from "
    "this portfolio's finished projects. Past-due parts are due now; parts warned as failing early come "
    "due within three years. The band shows the spread from replacement cost alone: early failures and "
    "deferred work aren't in it, so the real range is wider."
)


def forecast_all(db: Session, settings: ForecastSettings | None = None) -> list[Forecast]:
    invoices = list(db.scalars(select(Invoice)))
    if not invoices:
        return []
    components = list(db.scalars(select(ReserveComponent)))
    associations = list(db.scalars(select(Association).order_by(Association.id)))
    spend = spend_from_matches(reviewed_matches(db), invoices)
    done = completed_projects(components, associations, spend)
    ratios = cost_ratios(done)
    failing = set(
        db.scalars(
            select(ReviewItem.component_id).where(
                ReviewItem.warning_kind == "failing_early", ReviewItem.status.in_(("open", "confirmed"))
            )
        )
    )
    first = min(i.invoice_date.year for i in invoices)
    as_of = max(i.invoice_date.year for i in invoices)
    return [
        forecast_association(a, components, spend, done, ratios, failing, first, as_of, settings) for a in associations
    ]


def forecast_both(db: Session) -> dict[str, list[Forecast]]:
    """Both contribution modes; flat is the default the board leads with."""
    return {mode: forecast_all(db, ForecastSettings(contributions=mode)) for mode in ("flat", "rising")}
