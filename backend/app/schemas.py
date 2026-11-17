"""
API request/response schemas (Pydantic v2).

Response models decouple the public API from the ORM: internal columns can change without
breaking the frontend, and FastAPI publishes these shapes in the OpenAPI document (/docs).
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Me(BaseModel):
    username: str
    role: str


# ------------------------------------------------------------------------------- review queue
class ReviewItemOut(_ORM):
    id: str
    kind: str
    warning_kind: str | None
    association_id: str
    component_id: str | None
    invoice_id: str | None
    title: str
    detail: str
    amount_at_stake: float
    opened_on: date
    status: str


class ReviewItemPage(BaseModel):
    items: list[ReviewItemOut]
    total: int
    limit: int
    offset: int


class ReviewActionOut(_ORM):
    id: int
    action: str
    comment: str | None
    status_before: str | None
    status_after: str
    match_before: dict | None
    match_after: dict | None
    username: str
    role: str
    created_at: datetime


class RelatedInvoice(BaseModel):
    id: str
    invoice_date: date
    vendor_name: str
    memo: str
    amount: float
    fund_booked: str
    label: str
    component_id: str | None
    method: str
    role: Literal["evidence", "candidate"]  # behind the warning, or possibly the missing replacement


class ReviewItemDetail(ReviewItemOut):
    payload: dict
    invoices: list[RelatedInvoice]
    actions: list[ReviewActionOut]


class ReviewDecisionIn(BaseModel):
    action: Literal["confirm", "dismiss", "reopen", "comment"]
    comment: str | None = Field(default=None, max_length=4000)


class AssignmentIn(BaseModel):
    component_id: str | None = Field(description="the part this invoice was for; null means routine upkeep")
    comment: str | None = Field(default=None, max_length=4000)


class QueueChanges(BaseModel):
    opened: list[str]
    reopened: list[str]
    resolved_by_rerun: list[str]


class AssignmentOut(BaseModel):
    item: ReviewItemOut
    changes: QueueChanges


class ComponentOut(_ORM):
    id: str
    association_id: str
    category: str
    name: str
    location: str | None
    useful_life_years: int
    remaining_life_years: int
    replacement_cost: float
    planned_year: int


class BoardAssociation(BaseModel):
    id: str
    name: str
    kind: str
    town: str
    units: int
    status: Literal["red", "amber", "green"]
    reasons: list[str]
    open_warnings: int
    confirmed_warnings: int
    unplaced_invoices: int
    unplaced_amount: float


class BoardOut(BaseModel):
    synced: bool  # False until the review queue has been built once; the board would read all green
    rule: str
    associations: list[BoardAssociation]


class ForecastOut(BaseModel):
    association_id: str
    as_of: int
    start_balance: float
    history: list[dict]
    years: list[dict]
    share_short: float
    first_short_year: int | None
    due: dict[str, int]


class ForecastRow(BaseModel):
    association_id: str
    name: str
    status: str
    start_balance: float
    annual_contribution: float
    share_short: float
    first_short_year: int | None
    lowest_p50_in_contributions: float  # deepest median balance, in years of contributions
    start_balance_rising: float
    share_short_rising: float
    first_short_year_rising: int | None


class ForecastBoard(BaseModel):
    as_of: int | None
    assumptions: str
    associations: list[ForecastRow]


class AssociationTimeline(BaseModel):
    id: str
    name: str
    kind: str
    town: str
    units: int
    buildings: int
    study_year: int
    inflation_rate: float
    annual_contribution: float
    reserve_balance_start: float
    status: BoardAssociation
    years: list[dict]
    parts: list[dict]
    warnings: list[ReviewItemOut]
    forecast: ForecastOut | None  # flat contributions
    forecast_rising: ForecastOut | None
    forecast_assumptions: str
