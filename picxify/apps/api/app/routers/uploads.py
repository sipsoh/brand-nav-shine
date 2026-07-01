import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models.upload import FileStatus, UploadedFile
from app.models.user import User
from app.models.workspace import Membership, WorkspaceRole
from app.services.permissions import require_membership
from app.services.storage import PRESIGN_EXPIRY_SECONDS, StorageService, get_storage
from app.services.upload_validation import validate_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])

UPLOADER_ROLES = (
    WorkspaceRole.OWNER.value,
    WorkspaceRole.ADMIN.value,
    WorkspaceRole.EDITOR.value,
)


class PresignRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: uuid.UUID = Field(alias="workspaceId")
    filename: str = Field(min_length=1, max_length=500)
    mime_type: str | None = Field(default=None, alias="mimeType", max_length=255)
    size_bytes: int = Field(alias="sizeBytes")


class PresignResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_id: uuid.UUID = Field(alias="fileId")
    upload_url: str = Field(alias="uploadUrl")
    object_key: str = Field(alias="objectKey")
    expires_in_seconds: int = Field(alias="expiresInSeconds")


class CompleteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_id: uuid.UUID = Field(alias="fileId")
    status: str


@router.post("/presign", response_model=PresignResponse)
def presign_upload(
    body: PresignRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
) -> PresignResponse:
    require_membership(db, body.workspace_id, user, roles=UPLOADER_ROLES)

    # Plan-based limits arrive with billing (Milestone 10); everyone is on the
    # free limit until then.
    safe_name = validate_upload(
        body.filename, body.mime_type, body.size_bytes, max_mb=settings.max_upload_mb_free
    )

    file_id = uuid.uuid4()
    object_key = f"workspaces/{body.workspace_id}/uploads/{file_id}/{safe_name}"

    uploaded_file = UploadedFile(
        id=file_id,
        workspace_id=body.workspace_id,
        uploaded_by=user.id,
        original_filename=safe_name,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        object_key=object_key,
        status=FileStatus.PENDING.value,
    )
    db.add(uploaded_file)
    db.commit()

    return PresignResponse(
        file_id=file_id,
        upload_url=storage.presign_put(object_key, body.mime_type),
        object_key=object_key,
        expires_in_seconds=PRESIGN_EXPIRY_SECONDS,
    )


@router.post("/{file_id}/complete", response_model=CompleteResponse)
def complete_upload(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
) -> CompleteResponse:
    uploaded_file = db.scalar(select(UploadedFile).where(UploadedFile.id == file_id))
    if uploaded_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    require_membership(db, uploaded_file.workspace_id, user, roles=UPLOADER_ROLES)

    if uploaded_file.status == FileStatus.UPLOADED.value:
        return CompleteResponse(file_id=uploaded_file.id, status=uploaded_file.status)
    if uploaded_file.status != FileStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File is in state '{uploaded_file.status}' and cannot be completed.",
        )

    stat = storage.stat_object(uploaded_file.object_key)
    if stat is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="We did not receive the file in storage. Please retry the upload.",
        )

    max_bytes = settings.max_upload_mb_free * 1024 * 1024
    if stat.size_bytes > max_bytes:
        uploaded_file.status = FileStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"This file is too large for your plan (max {settings.max_upload_mb_free} MB).",
        )

    uploaded_file.size_bytes = stat.size_bytes
    uploaded_file.status = FileStatus.UPLOADED.value
    db.commit()
    return CompleteResponse(file_id=uploaded_file.id, status=uploaded_file.status)
