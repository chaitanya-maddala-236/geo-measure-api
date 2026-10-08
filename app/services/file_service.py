"""File processing orchestration and persistence."""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO
from uuid import uuid4

import geopandas as gpd
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.exceptions import APIError, ProcessingError
from app.db.models import Feature, GeoFile
from app.schemas.files import FeatureMeasurement, MeasurementCollection
from app.services.geospatial_service import read_geospatial_file
from app.services.measurement_service import measure_geometries
from app.utils.serialization import json_compatible

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


class FileService:
    """Validate uploads, process geospatial features and persist results."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def process_upload(self, uploaded_name: str, source: BinaryIO) -> GeoFile:
        """Process a KML/ZIP upload and return its durable file record."""
        started = time.monotonic()
        filename = _safe_filename(uploaded_name)
        extension = Path(filename).suffix.lower()
        if extension not in {".kml", ".zip"}:
            raise APIError("Only .kml and .zip uploads are supported.", status_code=415)

        file_type = "KML" if extension == ".kml" else "SHAPEFILE_ZIP"
        logger.info("Upload started filename=%s file_type=%s", filename, file_type)

        with TemporaryDirectory(prefix="geomeasure-") as temp_name:
            work_directory = Path(temp_name)
            input_path = work_directory / f"upload{extension}"
            size = _copy_with_limit(
                source, input_path, self.settings.max_upload_size_bytes
            )
            logger.info("Upload received filename=%s bytes=%d", filename, size)

            record = GeoFile(
                id=uuid4().hex,
                filename=filename,
                file_type=file_type,
                status="PROCESSING",
                feature_count=0,
            )
            self.db.add(record)
            self.db.commit()
            logger.info("Processing started file_id=%s", record.id)

            try:
                gdf = read_geospatial_file(
                    input_path,
                    file_type,
                    work_directory,
                    self.settings.max_archive_uncompressed_bytes,
                )
                self._persist_features(record, gdf)
                record.status = "COMPLETED"
                logger.info(
                    "Processing completed file_id=%s features=%d duration_seconds=%.3f",
                    record.id,
                    record.feature_count,
                    time.monotonic() - started,
                )
            except ProcessingError as exc:
                record.status = "FAILED"
                record.error_message = exc.message
                logger.info(
                    "Processing failed file_id=%s reason=%s duration_seconds=%.3f",
                    record.id,
                    exc.message,
                    time.monotonic() - started,
                )
            except Exception:
                record.status = "FAILED"
                record.error_message = "The uploaded file could not be processed."
                logger.exception(
                    "Unexpected processing failure file_id=%s duration_seconds=%.3f",
                    record.id,
                    time.monotonic() - started,
                )

            record.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(record)
            return record

    def _persist_features(self, record: GeoFile, gdf: gpd.GeoDataFrame) -> None:
        """Extract source geometry/attributes and persist per-feature outcomes."""
        source_crs = gdf.crs.to_string() if gdf.crs is not None else None
        record.source_crs = source_crs
        geometries = list(gdf.geometry)
        measurements = measure_geometries(geometries, source_crs)
        logger.info("Source CRS detected file_id=%s crs=%s", record.id, source_crs)
        logger.info("Feature count file_id=%s count=%d", record.id, len(gdf))

        rows: list[Feature] = []
        geometry_column = gdf.geometry.name
        for feature_index, (row, geometry, result) in enumerate(
            zip(gdf.iterrows(), geometries, measurements, strict=True)
        ):
            _, properties_row = row
            properties = {
                str(name): json_compatible(value)
                for name, value in properties_row.items()
                if name != geometry_column
            }
            geometry_data = (
                json_compatible(mapping(geometry)) if geometry is not None else None
            )
            rows.append(
                Feature(
                    file_id=record.id,
                    feature_index=feature_index,
                    geometry_type=(
                        geometry.geom_type if geometry is not None else "None"
                    ),
                    geometry=geometry_data,
                    properties=properties,
                    measurement=result.value,
                    measurement_type=result.measurement_type,
                    measurement_unit=result.unit,
                    measurement_status=result.status,
                    measurement_crs=result.measurement_crs,
                    measurement_error=result.error,
                )
            )

        self.db.add_all(rows)
        record.feature_count = len(rows)
        if source_crs is None and any(
            row.measurement_status == "ERROR" for row in rows
        ):
            record.error_message = (
                "Source CRS is missing; area and length measurements are unavailable."
            )

    def get_file(self, file_id: str) -> GeoFile:
        """Load a file record or raise a public not-found error."""
        record = self.db.get(GeoFile, file_id)
        if record is None:
            raise APIError("File not found.", status_code=404)
        return record

    def get_measurements(self, file_id: str) -> MeasurementCollection:
        """Load the feature list and serialize its measurement results."""
        statement = (
            select(GeoFile)
            .where(GeoFile.id == file_id)
            .options(selectinload(GeoFile.features))
        )
        record = self.db.scalar(statement)
        if record is None:
            raise APIError("File not found.", status_code=404)
        features = [
            FeatureMeasurement(
                feature_index=feature.feature_index,
                geometry_type=feature.geometry_type,
                geometry=feature.geometry,
                crs=record.source_crs,
                properties=feature.properties,
                measurement=feature.measurement,
                measurement_type=feature.measurement_type,
                measurement_unit=feature.measurement_unit,
                measurement_status=feature.measurement_status,
                measurement_crs=feature.measurement_crs,
                measurement_error=feature.measurement_error,
            )
            for feature in record.features
        ]
        return MeasurementCollection(
            file_id=record.id,
            filename=record.filename,
            feature_count=record.feature_count,
            source_crs=record.source_crs,
            status=record.status,
            features=features,
        )


def _safe_filename(filename: str) -> str:
    """Strip directory components from both Unix and Windows upload names."""
    basename = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    basename = "".join(character for character in basename if character.isprintable())
    return basename[:255]


def _copy_with_limit(source: BinaryIO, destination: Path, limit: int) -> int:
    """Copy an upload in bounded chunks and enforce the configured byte cap."""
    source.seek(0)
    total = 0
    try:
        with destination.open("wb") as target:
            while chunk := source.read(CHUNK_SIZE):
                total += len(chunk)
                if total > limit:
                    raise APIError("The upload exceeds the configured size limit.", 413)
                target.write(chunk)
    except APIError:
        raise
    except OSError as exc:
        raise APIError("The uploaded file could not be read.", status_code=400) from exc
    if total == 0:
        raise APIError("The uploaded file is empty.", 400)
    return total
