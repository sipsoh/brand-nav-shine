import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models.dashboard import Dashboard, DashboardVersion, DashboardVisibility
from app.models.dataset import Dataset, DatasetTable
from app.models.job import GenerationJob, JobStatus
from app.models.user import User
from app.models.workspace import WorkspaceRole
from app.services.permissions import require_membership

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])

EDITOR_ROLES = (
    WorkspaceRole.OWNER.value,
    WorkspaceRole.ADMIN.value,
    WorkspaceRole.EDITOR.value,
)

GenerateDispatcher = Callable[[uuid.UUID, uuid.UUID], None]


def get_generate_dispatcher() -> GenerateDispatcher:
    def dispatch(dashboard_id: uuid.UUID, job_id: uuid.UUID) -> None:
        from app.workers.tasks import generate_dashboard_job

        try:
            generate_dashboard_job.delay(str(dashboard_id), str(job_id))
        except Exception:
            logger.warning(
                "Celery broker unavailable; generating dashboard %s inline.", dashboard_id
            )
            generate_dashboard_job.run(str(dashboard_id), str(job_id))

    return dispatch


class GenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: uuid.UUID = Field(alias="workspaceId")
    dataset_id: uuid.UUID = Field(alias="datasetId")
    table_id: uuid.UUID | None = Field(default=None, alias="tableId")
    audience: str = "client"
    use_case_hint: str | None = Field(default=None, alias="useCaseHint")
    title_hint: str | None = Field(default=None, alias="titleHint", max_length=120)


class GenerateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dashboard_id: uuid.UUID = Field(alias="dashboardId")
    job_id: uuid.UUID = Field(alias="jobId")
    status: str


class VersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version_id: uuid.UUID = Field(alias="versionId")
    version_number: int = Field(alias="versionNumber")
    spec: dict
    generation_metadata: dict = Field(alias="generationMetadata")


class DashboardResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dashboard_id: uuid.UUID = Field(alias="dashboardId")
    title: str
    subtitle: str | None
    visibility: str
    dataset_id: uuid.UUID | None = Field(alias="datasetId")
    current_version: VersionResponse | None = Field(alias="currentVersion")


class DashboardListItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dashboard_id: uuid.UUID = Field(alias="dashboardId")
    title: str
    visibility: str
    created_at: datetime = Field(alias="createdAt")
    has_version: bool = Field(alias="hasVersion")


class DashboardListResponse(BaseModel):
    dashboards: list[DashboardListItem]

    model_config = ConfigDict(populate_by_name=True)


AUDIENCES = {"executive", "client", "investor", "team", "analyst", "public"}


@router.post("/generate", response_model=GenerateResponse)
def generate_dashboard(
    body: GenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    dispatch: GenerateDispatcher = Depends(get_generate_dispatcher),
) -> GenerateResponse:
    require_membership(db, body.workspace_id, user, roles=EDITOR_ROLES)
    if body.audience not in AUDIENCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audience must be one of {sorted(AUDIENCES)}.",
        )

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == body.dataset_id, Dataset.workspace_id == body.workspace_id
        )
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    if dataset.row_count is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This dataset has not finished processing yet.",
        )

    if body.table_id is not None:
        table = db.scalar(
            select(DatasetTable).where(
                DatasetTable.id == body.table_id, DatasetTable.dataset_id == dataset.id
            )
        )
        if table is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That sheet does not belong to this dataset.",
            )

    dashboard = Dashboard(
        workspace_id=body.workspace_id,
        dataset_id=dataset.id,
        title=(body.title_hint or f"{dataset.name} Report")[:200],
        visibility=DashboardVisibility.PRIVATE.value,
        created_by=user.id,
    )
    db.add(dashboard)
    db.flush()

    job = GenerationJob(
        workspace_id=body.workspace_id,
        user_id=user.id,
        dataset_id=dataset.id,
        dashboard_id=dashboard.id,
        job_type="generate_dashboard",
        status=JobStatus.QUEUED.value,
        input={
            "audience": body.audience,
            "useCaseHint": body.use_case_hint,
            "titleHint": body.title_hint,
            "tableId": str(body.table_id) if body.table_id else None,
        },
    )
    db.add(job)
    db.commit()

    dispatch(dashboard.id, job.id)
    return GenerateResponse(dashboard_id=dashboard.id, job_id=job.id, status=JobStatus.QUEUED.value)


@router.get("", response_model=DashboardListResponse)
def list_dashboards(
    workspace_id: uuid.UUID = Query(alias="workspaceId"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardListResponse:
    require_membership(db, workspace_id, user)
    dashboards = db.scalars(
        select(Dashboard)
        .where(Dashboard.workspace_id == workspace_id, Dashboard.deleted_at.is_(None))
        .order_by(Dashboard.created_at.desc())
    ).all()
    return DashboardListResponse(
        dashboards=[
            DashboardListItem(
                dashboard_id=d.id,
                title=d.title,
                visibility=d.visibility,
                created_at=d.created_at,
                has_version=d.current_version_id is not None,
            )
            for d in dashboards
        ]
    )


@router.get("/{dashboard_id}", response_model=DashboardResponse)
def get_dashboard(
    dashboard_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    dashboard = db.scalar(
        select(Dashboard).where(Dashboard.id == dashboard_id, Dashboard.deleted_at.is_(None))
    )
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found.")
    require_membership(db, dashboard.workspace_id, user)

    version = None
    if dashboard.current_version_id is not None:
        row = db.scalar(
            select(DashboardVersion).where(DashboardVersion.id == dashboard.current_version_id)
        )
        if row is not None:
            version = VersionResponse(
                version_id=row.id,
                version_number=row.version_number,
                spec=row.spec,
                generation_metadata=row.generation_metadata,
            )

    return DashboardResponse(
        dashboard_id=dashboard.id,
        title=dashboard.title,
        subtitle=dashboard.subtitle,
        visibility=dashboard.visibility,
        dataset_id=dashboard.dataset_id,
        current_version=version,
    )
