import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("uploaded_files.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    snapshot_object_key: Mapped[str | None] = mapped_column(String(1000))
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tables: Mapped[list["DatasetTable"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetTable.name"
    )
    findings: Mapped[list["DataQualityFinding"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DatasetTable(Base):
    __tablename__ = "dataset_tables"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_object_key: Mapped[str | None] = mapped_column(String(1000))
    profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sample_rows: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dataset: Mapped[Dataset] = relationship(back_populates="tables")
    columns: Mapped[list["DatasetColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="DatasetColumn.position"
    )


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_type: Mapped[str] = mapped_column(String(30), nullable=False)
    semantic_type: Mapped[str | None] = mapped_column(String(50))
    role_hint: Mapped[str | None] = mapped_column(String(20))
    nullable_ratio: Mapped[float | None] = mapped_column(Numeric(5, 4))
    unique_ratio: Mapped[float | None] = mapped_column(Numeric(5, 4))
    stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    examples: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    table: Mapped[DatasetTable] = relationship(back_populates="columns")


class DataQualityFinding(Base):
    __tablename__ = "data_quality_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE")
    )
    column_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("dataset_columns.id", ondelete="SET NULL")
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dataset: Mapped[Dataset] = relationship(back_populates="findings")
