"""dataset_files — many uploaded files per dataset

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-02

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dataset_files = op.create_table(
        "dataset_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("uploaded_files.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_dataset_files_dataset_id", "dataset_files", ["dataset_id"])

    # Backfill: every existing dataset's single file becomes its first
    # DatasetFile row, so the pipeline's "read all linked files" path covers
    # datasets created before this migration too. UUIDs are generated in
    # Python (not gen_random_uuid()) so this doesn't depend on pgcrypto.
    bind = op.get_bind()
    datasets = sa.table(
        "datasets", sa.column("id", sa.Uuid()), sa.column("file_id", sa.Uuid())
    )
    rows = bind.execute(
        sa.select(datasets.c.id, datasets.c.file_id).where(datasets.c.file_id.isnot(None))
    ).fetchall()
    if rows:
        bind.execute(
            dataset_files.insert(),
            [
                {"id": uuid.uuid4(), "dataset_id": row.id, "file_id": row.file_id, "position": 0}
                for row in rows
            ],
        )


def downgrade() -> None:
    op.drop_table("dataset_files")
