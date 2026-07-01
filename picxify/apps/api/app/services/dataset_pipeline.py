"""The parse/profile pipeline behind `parse_dataset` jobs (SETUP.md §9, steps C-F).

Pure orchestration over parser -> normalization -> profiler, persisting results
and job progress. Deliberately framework-light so tests can run it directly with
a test session and a fake storage service.
"""

import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset import DataQualityFinding, Dataset, DatasetColumn, DatasetTable
from app.models.job import GenerationJob, JobStatus
from app.models.upload import FileStatus, UploadedFile
from app.services.normalization import normalize_table, snake_case
from app.services.parser import ParseError, parse_file
from app.services.profiler import profile_table

logger = logging.getLogger(__name__)

PROGRESS_STEPS = [
    (10, "Reading file"),
    (35, "Cleaning data"),
    (60, "Detecting columns"),
    (85, "Saving dataset profile"),
]


def run_parse_dataset(db: Session, storage, dataset_id: uuid.UUID, job_id: uuid.UUID) -> None:
    job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
    if job is None or dataset is None:
        logger.error("parse_dataset: missing job %s or dataset %s", job_id, dataset_id)
        return

    uploaded_file = db.scalar(select(UploadedFile).where(UploadedFile.id == dataset.file_id))
    try:
        _run(db, storage, dataset, uploaded_file, job)
    except ParseError as error:
        _fail(db, job, dataset, uploaded_file, str(error))
    except Exception:
        logger.exception("parse_dataset failed (job=%s dataset=%s)", job_id, dataset_id)
        _fail(
            db,
            job,
            dataset,
            uploaded_file,
            "Something went wrong while processing this file. Please try again.",
        )


def _run(
    db: Session,
    storage,
    dataset: Dataset,
    uploaded_file: UploadedFile | None,
    job: GenerationJob,
) -> None:
    if uploaded_file is None:
        raise ParseError("The uploaded file for this dataset no longer exists.")

    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.now(timezone.utc)
    _progress(db, job, *PROGRESS_STEPS[0])

    data = storage.get_bytes(uploaded_file.object_key)
    raw_tables = parse_file(uploaded_file.original_filename, data)

    _progress(db, job, *PROGRESS_STEPS[1])
    total_rows = 0
    table_ids: list[str] = []

    for raw in raw_tables:
        normalized = normalize_table(raw.dataframe)
        _progress(db, job, *PROGRESS_STEPS[2])
        profile = profile_table(normalized.dataframe, normalized.type_hints)

        table = DatasetTable(
            dataset_id=dataset.id,
            name=raw.name,
            normalized_name=snake_case(raw.name),
            row_count=profile.row_count,
            column_count=profile.column_count,
            profile={
                "columns": [c.normalized_name for c in profile.columns],
            },
            sample_rows=profile.sample_rows,
        )
        db.add(table)
        db.flush()
        table_ids.append(str(table.id))
        total_rows += profile.row_count

        columns_by_name: dict[str, DatasetColumn] = {}
        for position, column_profile in enumerate(profile.columns):
            column = DatasetColumn(
                table_id=table.id,
                position=position,
                name=column_profile.name,
                normalized_name=column_profile.normalized_name,
                detected_type=column_profile.detected_type,
                role_hint=column_profile.role_hint,
                nullable_ratio=column_profile.nullable_ratio,
                unique_ratio=column_profile.unique_ratio,
                stats=column_profile.stats,
                examples=column_profile.examples,
                confidence=column_profile.confidence,
            )
            db.add(column)
            columns_by_name[column_profile.name] = column
        db.flush()

        penalty = profile.quality_penalty
        for note in normalized.notes:
            if note.severity != "info":
                penalty += 0.05
            db.add(
                DataQualityFinding(
                    dataset_id=dataset.id,
                    table_id=table.id,
                    column_id=(
                        columns_by_name[note.column].id
                        if note.column and note.column in columns_by_name
                        else None
                    ),
                    severity=note.severity,
                    finding_type=note.finding_type,
                    message=note.message,
                    meta=note.meta,
                )
            )
        for finding in profile.findings:
            db.add(
                DataQualityFinding(
                    dataset_id=dataset.id,
                    table_id=table.id,
                    column_id=(
                        columns_by_name[finding["column"]].id
                        if finding.get("column") in columns_by_name
                        else None
                    ),
                    severity=finding["severity"],
                    finding_type=finding["finding_type"],
                    message=finding["message"],
                    meta=finding.get("meta", {}),
                )
            )

        table.snapshot_object_key = _write_snapshot(
            storage, dataset, table.normalized_name, normalized.dataframe
        )

        table_quality = max(0.0, 1.0 - penalty)
        table.profile = {
            "columns": [c.normalized_name for c in profile.columns],
            "qualityScore": round(table_quality, 4),
        }

    _progress(db, job, *PROGRESS_STEPS[3])

    all_findings = db.scalars(
        select(DataQualityFinding).where(DataQualityFinding.dataset_id == dataset.id)
    ).all()
    severity_penalty = sum(
        0.15 if f.severity == "critical" else 0.05 if f.severity == "warning" else 0.0
        for f in all_findings
    )
    dataset.quality_score = round(max(0.0, 1.0 - severity_penalty), 4)
    dataset.row_count = total_rows
    dataset.table_count = len(raw_tables)
    dataset.profile = {
        "tableCount": len(raw_tables),
        "rowCount": total_rows,
        "findingCounts": _finding_counts(all_findings),
    }

    uploaded_file.status = FileStatus.PARSED.value
    job.status = JobStatus.SUCCEEDED.value
    job.progress = 100
    job.current_step = "Done"
    job.output = {"datasetId": str(dataset.id), "tableIds": table_ids}
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def _write_snapshot(storage, dataset: Dataset, table_name: str, dataframe) -> str:
    buffer = BytesIO()
    dataframe.to_parquet(buffer, index=False)
    object_key = (
        f"workspaces/{dataset.workspace_id}/datasets/{dataset.id}/tables/{table_name}.parquet"
    )
    storage.put_bytes(object_key, buffer.getvalue(), content_type="application/octet-stream")
    return object_key


def _progress(db: Session, job: GenerationJob, progress: int, step: str) -> None:
    job.progress = progress
    job.current_step = step
    db.commit()


def _fail(
    db: Session,
    job: GenerationJob,
    dataset: Dataset,
    uploaded_file: UploadedFile | None,
    message: str,
) -> None:
    db.rollback()
    job.status = JobStatus.FAILED.value
    job.error_message = message
    job.finished_at = datetime.now(timezone.utc)
    if uploaded_file is not None:
        uploaded_file.status = FileStatus.FAILED.value
    db.commit()


def _finding_counts(findings) -> dict:
    counts = {"info": 0, "warning": 0, "critical": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts
