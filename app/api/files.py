"""File upload, metadata and measurement endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.database import get_db
from app.schemas.files import FileResponse, MeasurementCollection
from app.services.file_service import FileService

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", response_model=FileResponse, status_code=201)
def upload_file(
    upload: Annotated[UploadFile, File(description="A .kml file or .zip Shapefile")],
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """Validate, process and persist an uploaded geospatial file."""
    settings: Settings = db.info["settings"]
    record = FileService(db, settings).process_upload(
        upload.filename or "", upload.file
    )
    return FileResponse.model_validate(record)


@router.get("/{file_id}/", response_model=FileResponse)
def get_file(
    file_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """Return metadata and processing status for one uploaded file."""
    record = FileService(db, db.info["settings"]).get_file(file_id)
    return FileResponse.model_validate(record)


@router.get("/{file_id}/measurements/", response_model=MeasurementCollection)
def get_measurements(
    file_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> MeasurementCollection:
    """Return extracted features and their measurement results."""
    return FileService(db, db.info["settings"]).get_measurements(file_id)
