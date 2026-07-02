import logging
import uuid
from collections.abc import Callable
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.db import get_db
from app.models.assumption import Assumption, AssumptionStatus
from app.models.dataset import DataQualityFinding, Dataset, DatasetColumn, DatasetTable
from app.models.job import GenerationJob, JobStatus
from app.models.upload import FileStatus, UploadedFile
from app.models.user import User
from app.models.workspace import WorkspaceRole
from app.prompts.semantic_mapper_prompt import SEMANTIC_TYPES
from app.services.insight_engine import ColumnMeta, compute_insights, quality_insights
from app.services.llm import get_semantic_mapper_llm
from app.services.permissions import require_membership
from app.services.storage import StorageService, get_storage
from app.services.text_insights import compute_text_themes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])

EDITOR_ROLES = (
    WorkspaceRole.OWNER.value,
    WorkspaceRole.ADMIN.value,
    WorkspaceRole.EDITOR.value,
)

ParseDispatcher = Callable[[uuid.UUID, uuid.UUID], None]


def get_parse_dispatcher() -> ParseDispatcher:
    """Enqueue parsing on Celery; fall back to inline execution when no broker
    is reachable (keyless local dev). Tests override this dependency."""

    def dispatch(dataset_id: uuid.UUID, job_id: uuid.UUID) -> None:
        from app.workers.tasks import parse_dataset_job

        try:
            parse_dataset_job.delay(str(dataset_id), str(job_id))
        except Exception:
            logger.warning("Celery broker unavailable; parsing dataset %s inline.", dataset_id)
            parse_dataset_job.run(str(dataset_id), str(job_id))

    return dispatch


class DatasetFromFileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: uuid.UUID = Field(alias="workspaceId")
    file_id: uuid.UUID = Field(alias="fileId")
    name: str = Field(min_length=1, max_length=200)


class DatasetFromFileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: uuid.UUID = Field(alias="datasetId")
    job_id: uuid.UUID = Field(alias="jobId")
    status: str


class ColumnResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    name: str
    normalized_name: str = Field(alias="normalizedName")
    detected_type: str = Field(alias="detectedType")
    semantic_type: str | None = Field(alias="semanticType")
    role_hint: str | None = Field(alias="roleHint")
    nullable_ratio: float | None = Field(alias="nullableRatio")
    unique_ratio: float | None = Field(alias="uniqueRatio")
    stats: dict
    examples: list
    confidence: float | None


class TableResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    name: str
    normalized_name: str = Field(alias="normalizedName")
    row_count: int = Field(alias="rowCount")
    column_count: int = Field(alias="columnCount")
    sample_rows: list = Field(alias="sampleRows")
    columns: list[ColumnResponse]


class FindingResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    severity: str
    finding_type: str = Field(alias="findingType")
    message: str


class AssumptionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    label: str
    status: str
    confidence: float | None
    editable: bool
    source: str
    affected_columns: list = Field(alias="affectedColumns")


class DatasetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    name: str
    source_type: str = Field(alias="sourceType")
    row_count: int | None = Field(alias="rowCount")
    table_count: int = Field(alias="tableCount")
    quality_score: float | None = Field(alias="qualityScore")
    use_case_candidates: list = Field(alias="useCaseCandidates", default_factory=list)
    tables: list[TableResponse]
    findings: list[FindingResponse]
    assumptions: list[AssumptionResponse]


class AssumptionPatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str | None = None
    replacement: dict | None = None  # {"column": "...", "semanticType": "..."}


@router.post("/from-file", response_model=DatasetFromFileResponse)
def create_dataset_from_file(
    body: DatasetFromFileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    dispatch: ParseDispatcher = Depends(get_parse_dispatcher),
) -> DatasetFromFileResponse:
    require_membership(db, body.workspace_id, user, roles=EDITOR_ROLES)

    uploaded_file = db.scalar(
        select(UploadedFile).where(
            UploadedFile.id == body.file_id, UploadedFile.workspace_id == body.workspace_id
        )
    )
    if uploaded_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    if uploaded_file.status not in {FileStatus.UPLOADED.value, FileStatus.PARSED.value}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This file has not finished uploading.",
        )

    dataset = Dataset(
        workspace_id=body.workspace_id,
        file_id=uploaded_file.id,
        name=body.name,
        source_type="file",
        created_by=user.id,
    )
    db.add(dataset)
    db.flush()

    job = GenerationJob(
        workspace_id=body.workspace_id,
        user_id=user.id,
        dataset_id=dataset.id,
        job_type="parse_dataset",
        status=JobStatus.QUEUED.value,
        input={"fileId": str(uploaded_file.id)},
    )
    db.add(job)
    db.commit()

    dispatch(dataset.id, job.id)

    return DatasetFromFileResponse(
        dataset_id=dataset.id, job_id=job.id, status=JobStatus.QUEUED.value
    )


class TableInsightsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    table_id: uuid.UUID = Field(alias="tableId")
    table_name: str = Field(alias="tableName")
    facts: list[dict]
    insights: list[dict]


class DatasetInsightsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: uuid.UUID = Field(alias="datasetId")
    tables: list[TableInsightsResponse]


@router.get("/{dataset_id}/insights", response_model=DatasetInsightsResponse)
def get_dataset_insights(
    dataset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
) -> DatasetInsightsResponse:
    """Compute facts and insights from the normalized Parquet snapshots.

    Everything numeric here is calculated by code; the only LLM involvement is
    text-theme clustering, whose counts are re-derived by code from validated
    comment references.
    """
    dataset = db.scalar(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .options(selectinload(Dataset.tables).selectinload(DatasetTable.columns))
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    require_membership(db, dataset.workspace_id, user)

    use_case = (dataset.profile.get("useCaseCandidates") or [{}])[0].get("useCase")
    responses: list[TableInsightsResponse] = []
    for table in dataset.tables:
        if not table.snapshot_object_key:
            continue
        df = pd.read_parquet(BytesIO(storage.get_bytes(table.snapshot_object_key)))
        columns_meta = [
            ColumnMeta(
                name=column.name,
                detected_type=column.detected_type,
                semantic_type=column.semantic_type,
                role_hint=column.role_hint,
            )
            for column in table.columns
        ]
        result = compute_insights(df, table_id=str(table.id), columns=columns_meta)

        findings = db.scalars(
            select(DataQualityFinding).where(DataQualityFinding.table_id == table.id)
        ).all()
        result.insights.extend(quality_insights(findings, table_id=str(table.id)))

        if use_case in {"survey", "customer_feedback"}:
            comment_column = next(
                (c.name for c in table.columns if c.semantic_type == "comment"), None
            )
            if comment_column is not None:
                result.insights.extend(
                    compute_text_themes(
                        df, str(table.id), comment_column, llm=get_semantic_mapper_llm()
                    )
                )

        responses.append(
            TableInsightsResponse(
                table_id=table.id,
                table_name=table.name,
                facts=[fact.to_dict() for fact in result.facts],
                insights=[insight.to_dict() for insight in result.insights],
            )
        )

    return DatasetInsightsResponse(dataset_id=dataset.id, tables=responses)


@router.patch("/{dataset_id}/assumptions/{assumption_id}", response_model=AssumptionResponse)
def update_assumption(
    dataset_id: uuid.UUID,
    assumption_id: uuid.UUID,
    body: AssumptionPatchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssumptionResponse:
    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    require_membership(db, dataset.workspace_id, user, roles=EDITOR_ROLES)

    assumption = db.scalar(
        select(Assumption).where(
            Assumption.id == assumption_id, Assumption.dataset_id == dataset_id
        )
    )
    if assumption is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assumption not found.")
    if not assumption.editable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This assumption is not editable."
        )

    if body.status is not None:
        if body.status not in {AssumptionStatus.ACCEPTED.value, AssumptionStatus.REJECTED.value}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status must be 'accepted' or 'rejected'.",
            )
        assumption.status = body.status

    if body.replacement is not None:
        column_name = body.replacement.get("column")
        semantic_type = body.replacement.get("semanticType")
        if not column_name or semantic_type not in SEMANTIC_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Replacement needs a 'column' and a valid 'semanticType'.",
            )
        column = db.scalar(
            select(DatasetColumn)
            .join(DatasetColumn.table)
            .where(DatasetTable.dataset_id == dataset_id, DatasetColumn.name == column_name)
        )
        if column is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Column '{column_name}' not found in this dataset.",
            )
        column.semantic_type = semantic_type
        assumption.status = AssumptionStatus.ACCEPTED.value
        assumption.meta = {**assumption.meta, "replacement": body.replacement, "byUser": True}

    db.commit()
    return AssumptionResponse(
        id=assumption.id,
        label=assumption.label,
        status=assumption.status,
        confidence=float(assumption.confidence) if assumption.confidence is not None else None,
        editable=assumption.editable,
        source=assumption.source,
        affected_columns=assumption.affected_columns,
    )


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(
    dataset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetResponse:
    dataset = db.scalar(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .options(selectinload(Dataset.tables), selectinload(Dataset.findings))
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    require_membership(db, dataset.workspace_id, user)

    assumptions = db.scalars(
        select(Assumption)
        .where(Assumption.dataset_id == dataset.id)
        .order_by(Assumption.created_at)
    ).all()

    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        source_type=dataset.source_type,
        row_count=dataset.row_count,
        table_count=dataset.table_count,
        quality_score=float(dataset.quality_score) if dataset.quality_score is not None else None,
        use_case_candidates=dataset.profile.get("useCaseCandidates", []),
        assumptions=[
            AssumptionResponse(
                id=a.id,
                label=a.label,
                status=a.status,
                confidence=float(a.confidence) if a.confidence is not None else None,
                editable=a.editable,
                source=a.source,
                affected_columns=a.affected_columns,
            )
            for a in assumptions
        ],
        tables=[
            TableResponse(
                id=table.id,
                name=table.name,
                normalized_name=table.normalized_name,
                row_count=table.row_count,
                column_count=table.column_count,
                sample_rows=table.sample_rows,
                columns=[
                    ColumnResponse(
                        id=column.id,
                        name=column.name,
                        normalized_name=column.normalized_name,
                        detected_type=column.detected_type,
                        semantic_type=column.semantic_type,
                        role_hint=column.role_hint,
                        nullable_ratio=(
                            float(column.nullable_ratio)
                            if column.nullable_ratio is not None
                            else None
                        ),
                        unique_ratio=(
                            float(column.unique_ratio) if column.unique_ratio is not None else None
                        ),
                        stats=column.stats,
                        examples=column.examples,
                        confidence=(
                            float(column.confidence) if column.confidence is not None else None
                        ),
                    )
                    for column in table.columns
                ],
            )
            for table in dataset.tables
        ],
        findings=[
            FindingResponse(
                severity=finding.severity,
                finding_type=finding.finding_type,
                message=finding.message,
            )
            for finding in dataset.findings
        ],
    )
