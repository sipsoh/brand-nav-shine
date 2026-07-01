import re
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal
from app.db import get_db
from app.models.user import User
from app.models.workspace import Membership, Workspace, WorkspaceRole
from app.schemas.responses import UserResponse, UserSyncResponse, WorkspaceSummary

router = APIRouter(prefix="/users", tags=["users"])


def make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return f"{base[:200]}-{uuid.uuid4().hex[:6]}"


def default_workspace_name(principal: Principal) -> str:
    if principal.name:
        return f"{principal.name}'s Workspace"
    if principal.email:
        return f"{principal.email.split('@')[0]}'s Workspace"
    return "My Workspace"


@router.post("/sync", response_model=UserSyncResponse)
def sync_user(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> UserSyncResponse:
    """Upsert the authenticated user and guarantee they own at least one workspace.

    The web app calls this right after sign-in, so a brand-new signup lands in a
    ready-to-use default workspace.
    """
    user = db.scalar(select(User).where(User.auth_user_id == principal.auth_user_id))
    created = user is None
    if user is None:
        user = User(
            auth_user_id=principal.auth_user_id,
            email=principal.email or f"{principal.auth_user_id}@users.picxify.invalid",
            name=principal.name,
        )
        db.add(user)
        db.flush()
    else:
        if principal.email and principal.email != user.email:
            user.email = principal.email
        if principal.name and principal.name != user.name:
            user.name = principal.name

    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    if not memberships:
        name = default_workspace_name(principal)
        workspace = Workspace(name=name, slug=make_slug(name), created_by=user.id)
        db.add(workspace)
        db.flush()
        membership = Membership(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER.value
        )
        db.add(membership)
        db.flush()
        memberships = [membership]

    db.commit()

    return UserSyncResponse(
        user=UserResponse(id=user.id, email=user.email, name=user.name),
        workspaces=[
            WorkspaceSummary(
                id=m.workspace.id, name=m.workspace.name, slug=m.workspace.slug, role=m.role
            )
            for m in memberships
        ],
        created=created,
    )
