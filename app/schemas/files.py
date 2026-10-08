"""Response schemas for file records and extracted measurements."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FileResponse(BaseModel):
    """Public metadata for an uploaded file."""

    id: str
    filename: str
    file_type: str
    feature_count: int
    source_crs: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class FeatureMeasurement(BaseModel):
    """Extracted geometry, source properties and optional measurement."""

    feature_index: int
    geometry_type: str
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any]
    measurement: float | None
    measurement_type: str | None
    measurement_unit: str | None
    measurement_status: str
    measurement_crs: str | None
    measurement_error: str | None

    model_config = ConfigDict(from_attributes=True)


class MeasurementCollection(BaseModel):
    """Feature measurement results for an uploaded file."""

    file_id: str
    filename: str
    feature_count: int
    source_crs: str | None
    status: str
    features: list[FeatureMeasurement]
