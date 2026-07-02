import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AssumptionStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    SYSTEM = "system"


class AssumptionSource(str, enum.Enum):
    PROFILE = "profile"
    SEMANTIC_MAPPER = "semantic_mapper"
    USER = "user"
    TEMPLATE = "template"
    MODEL = "model"


class Assumption(Base):
    """Dataset-level assumptions surfaced to the user for review.

    Dashboard versions (Milestone 7) will reference these when a spec is
    generated; at this stage they belong to the dataset that produced them.
    """

    __tablename__ = "assumptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AssumptionStatus.NEEDS_REVIEW.value
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default=AssumptionSource.SEMANTIC_MAPPER.value
    )
    affected_columns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
