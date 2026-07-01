"""datasets, dataset_tables, dataset_columns, data_quality_findings, generation_jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("uploaded_files.id"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("snapshot_object_key", sa.String(length=1000), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("table_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_datasets_workspace_id", "datasets", ["workspace_id"])

    op.create_table(
        "dataset_tables",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_object_key", sa.String(length=1000), nullable=True),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("sample_rows", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_dataset_tables_dataset_id", "dataset_tables", ["dataset_id"])

    op.create_table(
        "dataset_columns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "table_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("detected_type", sa.String(length=30), nullable=False),
        sa.Column("semantic_type", sa.String(length=50), nullable=True),
        sa.Column("role_hint", sa.String(length=20), nullable=True),
        sa.Column("nullable_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("unique_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("examples", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_dataset_columns_table_id", "dataset_columns", ["table_id"])

    op.create_table(
        "data_quality_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "table_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_tables.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "column_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_columns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("finding_type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="ck_findings_severity"
        ),
    )
    op.create_index(
        "ix_data_quality_findings_dataset_id", "data_quality_findings", ["dataset_id"]
    )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("dashboard_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(length=200), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
    )
    op.create_index(
        "ix_generation_jobs_workspace_status", "generation_jobs", ["workspace_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("generation_jobs")
    op.drop_table("data_quality_findings")
    op.drop_table("dataset_columns")
    op.drop_table("dataset_tables")
    op.drop_table("datasets")
