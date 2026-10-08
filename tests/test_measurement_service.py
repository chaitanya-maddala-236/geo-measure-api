"""Deterministic tests for supported geometry and CRS behavior."""

import pytest
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

from app.services.measurement_service import measure_geometries


def test_polygon_area_is_calculated_in_square_meters() -> None:
    polygon = Polygon([(78, 17), (78.001, 17), (78.001, 17.001), (78, 17.001)])
    result = measure_geometries([polygon], "EPSG:4326")[0]
    assert result.status == "CALCULATED"
    assert result.measurement_type == "area"
    assert result.unit == "m²"
    assert result.value is not None and 10_000 < result.value < 20_000
    assert result.measurement_crs == "EPSG:32644"


def test_multipolygon_area_is_calculated() -> None:
    first = Polygon([(78, 17), (78.001, 17), (78.001, 17.001), (78, 17.001)])
    second = Polygon([(78.002, 17), (78.003, 17), (78.003, 17.001), (78.002, 17.001)])
    result = measure_geometries([MultiPolygon([first, second])], "EPSG:4326")[0]
    assert result.status == "CALCULATED"
    assert result.value is not None and result.value > 20_000


def test_linestring_length_is_calculated_in_meters() -> None:
    line = LineString([(78, 17), (78.001, 17)])
    result = measure_geometries([line], "EPSG:4326")[0]
    assert result.status == "CALCULATED"
    assert result.measurement_type == "length"
    assert result.unit == "m"
    assert result.value is not None and 100 < result.value < 120


def test_multilinestring_length_is_calculated() -> None:
    line = MultiLineString([[(78, 17), (78.001, 17)], [(78, 17), (78, 17.001)]])
    result = measure_geometries([line], "EPSG:4326")[0]
    assert result.status == "CALCULATED"
    assert result.value is not None and result.value > 200


@pytest.mark.parametrize("geometry", [Point(78, 17), MultiPoint([(78, 17), (79, 18)])])
def test_point_geometry_does_not_require_measurement(geometry) -> None:
    result = measure_geometries([geometry], None)[0]
    assert result.status == "NOT_REQUIRED"
    assert result.value is None


def test_unsupported_geometry_is_reported_without_error() -> None:
    result = measure_geometries([GeometryCollection([Point(78, 17)])], "EPSG:4326")[0]
    assert result.status == "UNSUPPORTED"
    assert result.value is None


def test_geographic_crs_is_transformed_to_local_utm_before_measurement() -> None:
    line = LineString([(78, 17), (78.001, 17)])
    result = measure_geometries([line], "EPSG:4326")[0]
    assert result.measurement_crs == "EPSG:32644"
    assert result.value == pytest.approx(106.4, rel=0.03)


def test_projected_meter_crs_is_used_as_measurement_crs() -> None:
    line = LineString([(500_000, 1_000_000), (500_010, 1_000_000)])
    result = measure_geometries([line], CRS.from_epsg(32644))[0]
    assert result.value == pytest.approx(10.0)
    assert result.measurement_crs == "EPSG:32644"


def test_missing_crs_fails_measurement_safely() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    result = measure_geometries([polygon], None)[0]
    assert result.status == "ERROR"
    assert result.value is None
    assert "Source CRS" in (result.error or "")
