"""assumptions

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assumptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="needs_review"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("editable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "source", sa.String(length=30), nullable=False, server_default="semantic_mapper"
        ),
        sa.Column("affected_columns", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'needs_review', 'rejected', 'system')",
            name="ck_assumptions_status",
        ),
    )
    op.create_index("ix_assumptions_dataset_id", "assumptions", ["dataset_id"])


def downgrade() -> None:
    op.drop_table("assumptions")
