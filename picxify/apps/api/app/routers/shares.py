"""Public share route — the only unauthenticated data endpoint.

A dashboard is reachable here only when its owner explicitly published it
(visibility unlisted/public) and it has a generated version. Everything else
reads as 404 so slugs cannot be probed for existence.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.dashboard import Dashboard, DashboardVersion, DashboardVisibility

router = APIRouter(prefix="/shares", tags=["shares"])


class ShareResponse(BaseModel):
    title: str
    subtitle: str | None
    visibility: str
    spec: dict


@router.get("/{slug}", response_model=ShareResponse)
def get_share(slug: str, db: Session = Depends(get_db)) -> ShareResponse:
    dashboard = db.scalar(
        select(Dashboard).where(Dashboard.share_slug == slug, Dashboard.deleted_at.is_(None))
    )
    if (
        dashboard is None
        or dashboard.visibility == DashboardVisibility.PRIVATE.value
        or dashboard.current_version_id is None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    version = db.scalar(
        select(DashboardVersion).where(DashboardVersion.id == dashboard.current_version_id)
    )
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return ShareResponse(
        title=dashboard.title,
        subtitle=dashboard.subtitle,
        visibility=dashboard.visibility,
        spec=version.spec,
    )
