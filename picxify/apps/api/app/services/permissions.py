import uuid
from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Membership

# Security rule (SETUP.md §12.2): never accept workspaceId alone as proof of access.
# Every workspace-scoped query goes through this membership check. Non-members get
# 404 (not 403) so workspace IDs are not enumerable.


def require_membership(
    db: Session,
    workspace_id: uuid.UUID,
    user: User,
    roles: Iterable[str] | None = None,
) -> Membership:
    membership = db.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    if roles is not None and membership.role not in set(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role does not permit this action.",
        )
    return membership
