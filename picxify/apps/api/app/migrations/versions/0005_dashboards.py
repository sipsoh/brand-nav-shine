"""dashboards, dashboard_versions

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id", sa.Uuid(), sa.ForeignKey("datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("template_code", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=500), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
        sa.Column("share_slug", sa.String(length=64), nullable=True),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("share_slug", name="uq_dashboards_share_slug"),
        sa.CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')", name="ck_dashboards_visibility"
        ),
    )
    op.create_index("ix_dashboards_workspace_id", "dashboards", ["workspace_id"])

    op.create_table(
        "dashboard_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "dashboard_id",
            sa.Uuid(),
            sa.ForeignKey("dashboards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("generation_metadata", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("dashboard_id", "version_number", name="uq_dashboard_version_number"),
    )
    op.create_index("ix_dashboard_versions_dashboard_id", "dashboard_versions", ["dashboard_id"])


def downgrade() -> None:
    op.drop_table("dashboard_versions")
    op.drop_table("dashboards")
