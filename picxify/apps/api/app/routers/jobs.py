import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models.job import GenerationJob
from app.models.user import User
from app.services.permissions import require_membership

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: uuid.UUID = Field(alias="jobId")
    job_type: str = Field(alias="jobType")
    status: str
    progress: int
    current_step: str | None = Field(alias="currentStep")
    error_message: str | None = Field(alias="errorMessage")
    output: dict


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobResponse:
    job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    require_membership(db, job.workspace_id, user)
    return JobResponse(
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        error_message=job.error_message,
        output=job.output,
    )
