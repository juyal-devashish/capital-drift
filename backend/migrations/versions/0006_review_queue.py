"""capital review queue

Revision ID: 0006review
Revises: 0005warnings
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006review"
down_revision: str | None = "0005warnings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("warning_kind", sa.String(length=20), nullable=True),
        sa.Column("association_id", sa.String(length=32), nullable=False),
        sa.Column("component_id", sa.String(length=40), nullable=True),
        sa.Column("invoice_id", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("amount_at_stake", sa.Float(), nullable=False),
        sa.Column("opened_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["association_id"], ["associations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["reserve_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("review_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_review_items_association_id"), ["association_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_review_items_status"), ["status"], unique=False)
    op.create_table(
        "review_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status_before", sa.String(length=20), nullable=True),
        sa.Column("status_after", sa.String(length=20), nullable=False),
        sa.Column("match_before", sa.JSON(), nullable=True),
        sa.Column("match_after", sa.JSON(), nullable=True),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["review_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("review_actions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_review_actions_item_id"), ["item_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("review_actions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_review_actions_item_id"))
    op.drop_table("review_actions")
    with op.batch_alter_table("review_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_review_items_status"))
        batch_op.drop_index(batch_op.f("ix_review_items_association_id"))
    op.drop_table("review_items")
