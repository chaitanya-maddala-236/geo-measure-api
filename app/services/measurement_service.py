"""Feature measurements with explicit CRS transformation and statuses."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from app.services.crs_service import select_measurement_crs
from app.utils.geometry_utils import reproject_geometry

MeasurementStatus = Literal["CALCULATED", "NOT_REQUIRED", "UNSUPPORTED", "ERROR"]


@dataclass(frozen=True)
class MeasurementResult:
    """Measurement value and its unit, status, CRS and optional error."""

    value: float | None
    measurement_type: str | None
    unit: str | None
    status: MeasurementStatus
    measurement_crs: str | None = None
    error: str | None = None


SUPPORTED_TYPES = {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}
logger = logging.getLogger(__name__)


def measure_geometries(
    geometries: Sequence[BaseGeometry | None], source_crs: CRS | str | None
) -> list[MeasurementResult]:
    """Calculate supported measurements after transforming to projected meters."""
    results: list[MeasurementResult | None] = [None] * len(geometries)
    measurable = [
        geometry
        for geometry in geometries
        if geometry is not None and geometry.geom_type in SUPPORTED_TYPES
    ]

    measurement_crs: CRS | None = None
    crs_error: str | None = None
    if measurable:
        if source_crs is None:
            crs_error = (
                "Source CRS is unavailable; measurement cannot be calculated safely."
            )
        else:
            try:
                measurement_crs = select_measurement_crs(source_crs, measurable)
                authority = measurement_crs.to_authority()
                label = ":".join(authority) if authority else "custom projected CRS"
                logger.info("Measurement CRS selected measurement_crs=%s", label)
            except Exception:
                crs_error = "A safe projected measurement CRS could not be selected."

    for index, geometry in enumerate(geometries):
        if geometry is None or geometry.geom_type not in SUPPORTED_TYPES:
            if geometry is not None and geometry.geom_type in POINT_TYPES:
                results[index] = MeasurementResult(None, None, None, "NOT_REQUIRED")
            else:
                results[index] = MeasurementResult(None, None, None, "UNSUPPORTED")
            continue

        if crs_error is not None or measurement_crs is None:
            results[index] = MeasurementResult(
                None,
                "area" if "Polygon" in geometry.geom_type else "length",
                "m²" if "Polygon" in geometry.geom_type else "m",
                "ERROR",
                error=crs_error or "Measurement CRS is unavailable.",
            )
            continue

        try:
            source = CRS.from_user_input(source_crs)
            if source.equals(measurement_crs):
                measured_geometry = geometry
            else:
                project = Transformer.from_crs(source, measurement_crs, always_xy=True)
                measured_geometry = reproject_geometry(geometry, project)

            if "Polygon" in geometry.geom_type:
                # measured_geometry is always in a projected CRS with meter units.
                value = float(measured_geometry.area)
                measurement_type, unit = "area", "m²"
            else:
                # measured_geometry is always in a projected CRS with meter units.
                value = float(measured_geometry.length)
                measurement_type, unit = "length", "m"
            results[index] = MeasurementResult(
                value, measurement_type, unit, "CALCULATED", measurement_crs.to_string()
            )
        except Exception:
            results[index] = MeasurementResult(
                None,
                "area" if "Polygon" in geometry.geom_type else "length",
                "m²" if "Polygon" in geometry.geom_type else "m",
                "ERROR",
                measurement_crs.to_string(),
                "The geometry could not be transformed or measured.",
            )

    return [result for result in results if result is not None]
