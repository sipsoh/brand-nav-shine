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

from app.models.assumption import Assumption, AssumptionSource, AssumptionStatus
from app.models.dataset import DataQualityFinding, Dataset, DatasetColumn, DatasetTable
from app.models.job import GenerationJob, JobStatus
from app.models.upload import FileStatus, UploadedFile
from app.services.llm import get_semantic_mapper_llm
from app.services.normalization import normalize_table, snake_case
from app.services.parser import ParseError, parse_file
from app.services.profiler import profile_table
from app.services.semantic_mapper import ColumnInput, TableInput, map_dataset

logger = logging.getLogger(__name__)

PROGRESS_STEPS = [
    (10, "Reading file"),
    (30, "Cleaning data"),
    (50, "Detecting columns"),
    (70, "Finding the story"),
    (90, "Saving dataset profile"),
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
    table_qualities: list[float] = []

    for raw in raw_tables:
        normalized = normalize_table(raw.dataframe, table_name=raw.name)
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
        for note in [*raw.notes, *normalized.notes]:
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
        table_qualities.append(table_quality)
        table.profile = {
            "columns": [c.normalized_name for c in profile.columns],
            "qualityScore": round(table_quality, 4),
        }

    _progress(db, job, *PROGRESS_STEPS[3])
    _apply_semantic_mapping(db, dataset, uploaded_file)

    _progress(db, job, *PROGRESS_STEPS[4])

    all_findings = db.scalars(
        select(DataQualityFinding).where(DataQualityFinding.dataset_id == dataset.id)
    ).all()
    # Average per-table quality: a 20-sheet workbook should not read as 0%
    # just because penalties accumulate across sheets.
    dataset.quality_score = round(
        sum(table_qualities) / len(table_qualities) if table_qualities else 0.0, 4
    )
    dataset.row_count = total_rows
    dataset.table_count = len(raw_tables)
    dataset.profile = {
        **dataset.profile,
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


def _apply_semantic_mapping(db: Session, dataset: Dataset, uploaded_file: UploadedFile) -> None:
    """Run the semantic mapper over the freshly profiled columns and persist
    semantic types, use-case candidates, and reviewable assumptions."""
    tables = db.scalars(select(DatasetTable).where(DatasetTable.dataset_id == dataset.id)).all()
    # The same column name often appears on many sheets (e.g. 'Duration' on every
    # per-category tab); a mapping for a name applies to all of them.
    columns_by_name: dict[str, list[DatasetColumn]] = {}
    table_inputs: list[TableInput] = []
    for table in tables:
        db_columns = db.scalars(
            select(DatasetColumn).where(DatasetColumn.table_id == table.id)
        ).all()
        column_inputs = []
        for column in db_columns:
            columns_by_name.setdefault(column.name, []).append(column)
            column_inputs.append(
                ColumnInput(
                    name=column.name,
                    normalized_name=column.normalized_name,
                    detected_type=column.detected_type,
                    role_hint=column.role_hint,
                    unique_ratio=(
                        float(column.unique_ratio) if column.unique_ratio is not None else None
                    ),
                    examples=column.examples,
                )
            )
        table_inputs.append(TableInput(name=table.name, columns=column_inputs))

    mapping = map_dataset(
        table_inputs,
        filename=uploaded_file.original_filename,
        llm=get_semantic_mapper_llm(),
    )

    for column_name, mapped in mapping.column_mappings.items():
        for column in columns_by_name.get(column_name, []):
            column.semantic_type = mapped.semantic_type
            column.role_hint = mapped.role

    for item in mapping.assumptions:
        db.add(
            Assumption(
                dataset_id=dataset.id,
                label=item["label"],
                status=AssumptionStatus.NEEDS_REVIEW.value,
                confidence=item["confidence"],
                editable=item["editable"],
                source=AssumptionSource.SEMANTIC_MAPPER.value,
                affected_columns=item.get("affected_columns", []),
            )
        )

    dataset.profile = {
        **dataset.profile,
        "useCaseCandidates": mapping.use_case_candidates,
        "semanticMapper": {"promptVersion": mapping.prompt_version, "usedLlm": mapping.used_llm},
    }


def _write_snapshot(storage, dataset: Dataset, table_name: str, dataframe) -> str:
    buffer = BytesIO()
    try:
        dataframe.to_parquet(buffer, index=False)
    except Exception:
        # Safety net for anything Arrow still cannot serialize: stringify the
        # offending object columns and retry once.
        import pandas as pd

        safe = dataframe.copy()
        for column in safe.columns:
            if pd.api.types.is_object_dtype(safe[column]):
                safe[column] = safe[column].map(lambda v: None if pd.isna(v) else str(v))
        buffer = BytesIO()
        safe.to_parquet(buffer, index=False)
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
