"""spend warnings

Revision ID: 0005warnings
Revises: 0004llm
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005warnings"
down_revision: str | None = "0004llm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spend_warnings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("association_id", sa.String(length=32), nullable=False),
        sa.Column("component_id", sa.String(length=40), nullable=False),
        sa.Column("fired_on", sa.Date(), nullable=False),
        sa.Column("headline", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("numbers", sa.JSON(), nullable=False),
        sa.Column("invoice_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["association_id"], ["associations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["reserve_components.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("spend_warnings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_spend_warnings_method"), ["method"], unique=False)
        batch_op.create_index(batch_op.f("ix_spend_warnings_association_id"), ["association_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_spend_warnings_component_id"), ["component_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("spend_warnings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_spend_warnings_component_id"))
        batch_op.drop_index(batch_op.f("ix_spend_warnings_association_id"))
        batch_op.drop_index(batch_op.f("ix_spend_warnings_method"))
    op.drop_table("spend_warnings")
