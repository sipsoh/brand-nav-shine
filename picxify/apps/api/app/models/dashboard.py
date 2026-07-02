import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DashboardVisibility(str, enum.Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class Dashboard(Base):
    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="SET NULL")
    )
    template_code: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DashboardVisibility.PRIVATE.value
    )
    share_slug: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Plain column (no FK) to avoid a circular constraint with dashboard_versions.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    versions: Mapped[list["DashboardVersion"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan"
    )


class DashboardVersion(Base):
    __tablename__ = "dashboard_versions"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "version_number", name="uq_dashboard_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dashboard: Mapped[Dashboard] = relationship(back_populates="versions")
