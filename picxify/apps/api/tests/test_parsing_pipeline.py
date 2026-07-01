import uuid
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.dataset import DataQualityFinding, Dataset, DatasetColumn, DatasetTable
from app.models.job import GenerationJob, JobStatus
from app.models.upload import FileStatus, UploadedFile
from app.models.user import User
from app.models.workspace import Membership, Workspace, WorkspaceRole
from app.services.dataset_pipeline import run_parse_dataset
from tests.conftest import TestingSession

SAMPLE_DATA = Path(__file__).resolve().parents[3] / "packages" / "sample-data"

MESSY_CSV = b"""campaign,spend,close_date,region
Spring Sale,"$1,250.00",2026-05-04,West
,,,
Brand Push,"$980.50",05/11/2026,
Retargeting,"$640.00",2026-05-25,East
Total,"$2,870.50",,
"""


class FakePipelineStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]

    def put_bytes(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        self.objects[object_key] = data


@pytest.fixture
def db():
    session = TestingSession()
    yield session
    session.close()


def seed(db, file_bytes: bytes, filename: str, storage: FakePipelineStorage):
    user = User(auth_user_id=f"user_{uuid.uuid4().hex[:8]}", email="p@example.com")
    db.add(user)
    db.flush()
    workspace = Workspace(name="W", created_by=user.id)
    db.add(workspace)
    db.flush()
    db.add(
        Membership(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER.value)
    )
    object_key = f"workspaces/{workspace.id}/uploads/{uuid.uuid4()}/{filename}"
    storage.objects[object_key] = file_bytes
    uploaded = UploadedFile(
        workspace_id=workspace.id,
        uploaded_by=user.id,
        original_filename=filename,
        size_bytes=len(file_bytes),
        object_key=object_key,
        status=FileStatus.UPLOADED.value,
    )
    db.add(uploaded)
    db.flush()
    dataset = Dataset(
        workspace_id=workspace.id,
        file_id=uploaded.id,
        name="Test Dataset",
        source_type="file",
        created_by=user.id,
    )
    db.add(dataset)
    db.flush()
    job = GenerationJob(
        workspace_id=workspace.id,
        user_id=user.id,
        dataset_id=dataset.id,
        job_type="parse_dataset",
    )
    db.add(job)
    db.commit()
    return dataset, job, uploaded


def test_pipeline_parses_clean_marketing_csv(db):
    storage = FakePipelineStorage()
    csv_bytes = (SAMPLE_DATA / "marketing_campaigns.csv").read_bytes()
    dataset, job, uploaded = seed(db, csv_bytes, "marketing_campaigns.csv", storage)

    run_parse_dataset(db, storage, dataset.id, job.id)

    db.refresh(job)
    db.refresh(dataset)
    db.refresh(uploaded)
    assert job.status == JobStatus.SUCCEEDED.value
    assert job.progress == 100
    assert uploaded.status == FileStatus.PARSED.value
    assert dataset.row_count == 16
    assert dataset.table_count == 1

    table = db.scalar(select(DatasetTable).where(DatasetTable.dataset_id == dataset.id))
    assert table.column_count == 8
    assert len(table.sample_rows) == 5
    assert table.snapshot_object_key in storage.objects  # parquet snapshot written

    columns = {
        c.name: c
        for c in db.scalars(select(DatasetColumn).where(DatasetColumn.table_id == table.id))
    }
    assert columns["date"].detected_type in {"date", "datetime"}
    assert columns["date"].role_hint == "date"
    assert columns["campaign"].detected_type == "category"
    assert columns["spend"].role_hint == "measure"
    assert columns["conversions"].detected_type == "integer"
    assert columns["spend"].stats["max"] is not None


def test_pipeline_handles_messy_csv(db):
    storage = FakePipelineStorage()
    dataset, job, _ = seed(db, MESSY_CSV, "messy.csv", storage)

    run_parse_dataset(db, storage, dataset.id, job.id)

    db.refresh(job)
    db.refresh(dataset)
    assert job.status == JobStatus.SUCCEEDED.value

    table = db.scalar(select(DatasetTable).where(DatasetTable.dataset_id == dataset.id))
    # 5 data lines -> blank row and Total footer removed -> 3 rows
    assert table.row_count == 3

    findings = db.scalars(
        select(DataQualityFinding).where(DataQualityFinding.dataset_id == dataset.id)
    ).all()
    finding_types = {f.finding_type for f in findings}
    assert "footer_rows_removed" in finding_types
    assert "missing_values" in finding_types  # region column is mostly empty

    columns = {
        c.name: c
        for c in db.scalars(select(DatasetColumn).where(DatasetColumn.table_id == table.id))
    }
    assert columns["spend"].role_hint == "measure"
    assert float(dataset.quality_score) < 1.0


def test_pipeline_parses_excel_with_multiple_sheets(db):
    storage = FakePipelineStorage()
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"deal": ["A", "B"], "amount": [100, 200]}).to_excel(
            writer, sheet_name="Pipeline", index=False
        )
        pd.DataFrame({"owner": ["Sam"], "quota": [5]}).to_excel(
            writer, sheet_name="Quotas", index=False
        )
        pd.DataFrame().to_excel(writer, sheet_name="Empty", index=False)
    dataset, job, _ = seed(db, buffer.getvalue(), "pipeline.xlsx", storage)

    run_parse_dataset(db, storage, dataset.id, job.id)

    db.refresh(job)
    db.refresh(dataset)
    assert job.status == JobStatus.SUCCEEDED.value
    assert dataset.table_count == 2  # empty sheet skipped

    tables = db.scalars(
        select(DatasetTable).where(DatasetTable.dataset_id == dataset.id)
    ).all()
    assert {t.name for t in tables} == {"Pipeline", "Quotas"}


def test_pipeline_fails_gracefully_on_empty_file(db):
    storage = FakePipelineStorage()
    dataset, job, uploaded = seed(db, b"", "empty.csv", storage)

    run_parse_dataset(db, storage, dataset.id, job.id)

    db.refresh(job)
    db.refresh(uploaded)
    assert job.status == JobStatus.FAILED.value
    assert job.error_message == "The file is empty."
    assert uploaded.status == FileStatus.FAILED.value
