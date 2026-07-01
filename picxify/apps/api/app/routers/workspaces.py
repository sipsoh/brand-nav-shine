import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.models.workspace import Membership, Workspace, WorkspaceRole
from app.routers.users import make_slug
from app.schemas.requests import WorkspaceCreateRequest
from app.schemas.responses import WorkspaceListResponse, WorkspaceSummary
from app.services.permissions import require_membership

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=WorkspaceListResponse)
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceListResponse:
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    return WorkspaceListResponse(
        workspaces=[
            WorkspaceSummary(
                id=m.workspace.id, name=m.workspace.name, slug=m.workspace.slug, role=m.role
            )
            for m in memberships
        ]
    )


@router.post("", response_model=WorkspaceSummary, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceSummary:
    workspace = Workspace(name=body.name, slug=make_slug(body.name), created_by=user.id)
    db.add(workspace)
    db.flush()
    membership = Membership(
        workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER.value
    )
    db.add(membership)
    db.commit()
    return WorkspaceSummary(
        id=workspace.id, name=workspace.name, slug=workspace.slug, role=membership.role
    )


@router.get("/{workspace_id}", response_model=WorkspaceSummary)
def get_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceSummary:
    membership = require_membership(db, workspace_id, user)
    workspace = membership.workspace
    return WorkspaceSummary(
        id=workspace.id, name=workspace.name, slug=workspace.slug, role=membership.role
    )
