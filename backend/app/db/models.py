"""
ORM models (SQLAlchemy 2.0 typed mappings).

Tables
------
portfolios             a property-management brand that runs several associations
associations           one homeowner or condo association, with its reserve fund position
reserve_components     one line of the association's reserve study: a building part with its
                       useful life, replacement cost and planned replacement year
invoices               vendor invoices as exported from the accounting system; the fund they were
                       booked to is the association's own coding, which can be wrong
invoice_matches        what each matcher (rules, llm, reviewer) decided for each invoice: routine,
                       repair or replacement of which component, with confidence, reasons and flags
llm_attempts           every invoice sent to Claude (or held back by the budget), with the outcome,
                       raw answer, token counts and errors; failures are kept, never dropped
spend_warnings         repair-or-replace warnings raised by watching each component's matched spend
                       against its plan (failing early, overdue, over budget), per matching method
review_items           the review queue: one row per warning or unsure invoice, keyed so it survives
                       reruns; property managers decide, reruns clear what no longer applies
review_actions         append-only log of every queue decision and invoice assignment, with the match
                       before and after; automatic changes from reruns are logged as user "system"

The answer key for synthetic data (true component per invoice, planted problems) is never stored
in these tables; see app/synth.

Money is stored as whole dollars in double precision.
"""

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. P01
    name: Mapped[str] = mapped_column(String(200))

    associations: Mapped[list["Association"]] = relationship(back_populates="portfolio", order_by="Association.id")


class Association(Base):
    __tablename__ = "associations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. A07
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))  # condo_midrise | garden | sfh_hoa
    town: Mapped[str] = mapped_column(String(80))
    units: Mapped[int] = mapped_column(Integer)
    buildings: Mapped[int] = mapped_column(Integer)
    year_built: Mapped[int] = mapped_column(Integer)
    # Reserve study the plan comes from, and the fund position on 1 January of that year.
    study_year: Mapped[int] = mapped_column(Integer)
    inflation_rate: Mapped[float] = mapped_column(Float)  # study's assumed annual cost inflation
    reserve_balance_start: Mapped[float] = mapped_column(Float)
    annual_contribution: Mapped[float] = mapped_column(Float)

    portfolio: Mapped[Portfolio] = relationship(back_populates="associations")
    components: Mapped[list["ReserveComponent"]] = relationship(
        back_populates="association", order_by="ReserveComponent.id"
    )


class ReserveComponent(Base):
    __tablename__ = "reserve_components"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # e.g. A07-ROOF-B
    association_id: Mapped[str] = mapped_column(ForeignKey("associations.id"), index=True)
    category: Mapped[str] = mapped_column(String(40))  # roofing, elevators, paving, ...
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(80))  # e.g. "Bldg B"; None = whole site
    useful_life_years: Mapped[int] = mapped_column(Integer)
    remaining_life_years: Mapped[int] = mapped_column(Integer)  # as of the study year
    replacement_cost: Mapped[float] = mapped_column(Float)  # in study-year dollars
    planned_year: Mapped[int] = mapped_column(Integer)

    association: Mapped[Association] = relationship(back_populates="components")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (Index("ix_invoices_association_date", "association_id", "invoice_date"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. INV-000123
    association_id: Mapped[str] = mapped_column(ForeignKey("associations.id"))
    vendor_name: Mapped[str] = mapped_column(String(200))  # as written on the invoice
    invoice_number: Mapped[str] = mapped_column(String(40))
    invoice_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    memo: Mapped[str] = mapped_column(Text)
    fund_booked: Mapped[str] = mapped_column(String(12))  # operating | reserve, as the books say


class InvoiceMatch(Base):
    """What one matcher decided about one invoice. Replaced on every run of that method.

    One row per (invoice, method), so the rules' answer and Claude's answer sit side by side.
    """

    __tablename__ = "invoice_matches"

    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), primary_key=True)
    method: Mapped[str] = mapped_column(String(20), primary_key=True)  # rules | llm | reviewer
    label: Mapped[str] = mapped_column(String(16))  # routine | repair | replacement | unsure
    component_id: Mapped[str | None] = mapped_column(ForeignKey("reserve_components.id"), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LLMAttemptRecord(Base):
    """Every invoice sent to (or held back from) Claude: answers, refusals, invalid output, errors."""

    __tablename__ = "llm_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12))  # ok | unsure | invalid | refused | truncated | error | budget
    model: Mapped[str] = mapped_column(String(60))
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    component_id: Mapped[str | None] = mapped_column(String(40))
    answer: Mapped[dict | None] = mapped_column(JSON)
    raw_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SpendWarningRecord(Base):
    """One repair-or-replace warning. Replaced on every watch run for the matching method it used."""

    __tablename__ = "spend_warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    method: Mapped[str] = mapped_column(String(20), index=True)  # matches used: rules | combined
    kind: Mapped[str] = mapped_column(String(20))  # failing_early | overdue | over_budget
    association_id: Mapped[str] = mapped_column(ForeignKey("associations.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[str] = mapped_column(ForeignKey("reserve_components.id", ondelete="CASCADE"), index=True)
    fired_on: Mapped[date] = mapped_column(Date)
    headline: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    numbers: Mapped[dict] = mapped_column(JSON, default=dict)
    invoice_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReviewItem(Base):
    """One thing in the capital review queue. The id is a stable key, so decisions survive reruns.

    Warnings: ``W:<kind>:<component>:<cycle year>``. Unsure invoices: ``I:<invoice id>``.
    """

    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(12))  # warning | invoice
    warning_kind: Mapped[str | None] = mapped_column(String(20))  # failing_early | overdue | over_budget
    association_id: Mapped[str] = mapped_column(ForeignKey("associations.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[str | None] = mapped_column(ForeignKey("reserve_components.id", ondelete="CASCADE"))
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text)
    amount_at_stake: Mapped[float] = mapped_column(Float)
    opened_on: Mapped[date] = mapped_column(Date)  # when the warning fired, or the invoice date
    status: Mapped[str] = mapped_column(String(20), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ReviewAction(Base):
    """Append-only audit log for the capital review queue. Rows are never updated or deleted."""

    __tablename__ = "review_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("review_items.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(20))  # confirm | dismiss | reopen | comment | assign | rerun
    comment: Mapped[str | None] = mapped_column(Text)
    status_before: Mapped[str | None] = mapped_column(String(20))
    status_after: Mapped[str] = mapped_column(String(20))
    match_before: Mapped[dict | None] = mapped_column(JSON)
    match_after: Mapped[dict | None] = mapped_column(JSON)
    username: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
