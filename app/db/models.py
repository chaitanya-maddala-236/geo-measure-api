"""Relational models for uploaded files and extracted features."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class GeoFile(Base):
    """An uploaded data file and its processing summary."""

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    features: Mapped[list["Feature"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="Feature.feature_index",
    )


class Feature(Base):
    """A source feature with GeoJSON geometry and its measurement result."""

    __tablename__ = "features"
    __table_args__ = (Index("ix_features_file_index", "file_id", "feature_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    measurement: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    measurement_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    measurement_status: Mapped[str] = mapped_column(String(16), nullable=False)
    measurement_crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    measurement_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped[GeoFile] = relationship(back_populates="features")
