"""Reading KML and Shapefile datasets into GeoDataFrames."""

import logging
from pathlib import Path

import geopandas as gpd

from app.core.exceptions import ProcessingError
from app.utils.archive import extract_shapefile_archive

logger = logging.getLogger(__name__)


def read_geospatial_file(
    input_path: Path,
    file_type: str,
    work_directory: Path,
    max_archive_uncompressed_bytes: int,
) -> gpd.GeoDataFrame:
    """Read a validated KML or Shapefile ZIP into a GeoDataFrame."""
    try:
        if file_type == "KML":
            return gpd.read_file(input_path, engine="pyogrio")
        extracted = work_directory / "shapefile"
        extracted.mkdir()
        shapefile_path = extract_shapefile_archive(
            input_path, extracted, max_archive_uncompressed_bytes
        )
        return gpd.read_file(shapefile_path, engine="pyogrio")
    except ProcessingError:
        raise
    except Exception as exc:
        logger.info("Geospatial parser rejected input (%s)", type(exc).__name__)
        message = (
            "The KML file could not be read."
            if file_type == "KML"
            else ("The Shapefile data could not be read.")
        )
        raise ProcessingError(message) from exc
