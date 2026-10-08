"""Shared API client and geospatial fixture builders."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Run an isolated app against a temporary SQLite database."""
    database_path = (tmp_path / "test.db").as_posix()
    app = create_app(Settings(database_url=f"sqlite:///{database_path}"))
    with TestClient(app) as test_client:
        yield test_client


def make_shapefile_zip(
    directory: Path, *, include_projection: bool = True, omit: set[str] | None = None
) -> bytes:
    """Create and zip a small square Shapefile for endpoint tests."""
    omit = omit or set()
    shapefile = directory / "boundary.shp"
    geometry = Polygon(
        [(78.0, 17.0), (78.001, 17.0), (78.001, 17.001), (78.0, 17.001), (78.0, 17.0)]
    )
    frame = gpd.GeoDataFrame(
        {"name": ["test parcel"]}, geometry=[geometry], crs="EPSG:4326"
    )
    if not include_projection:
        frame = frame.set_crs(None, allow_override=True)
    frame.to_file(shapefile, driver="ESRI Shapefile", engine="pyogrio")

    with ZipFile(directory / "shape.zip", "w", ZIP_DEFLATED) as archive:
        for component in shapefile.parent.glob("boundary.*"):
            if component.suffix.lower() not in omit:
                archive.write(component, component.name)
    return (directory / "shape.zip").read_bytes()


def make_kml(*placemarks: str) -> bytes:
    """Wrap placemark XML snippets in a small valid KML document."""
    body = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document>{}</Document></kml>""".format(
        "".join(placemarks)
    )
    return body.encode("utf-8")


@pytest.fixture
def shapefile_zip_factory():
    """Expose the Shapefile builder to tests using their own temp folder."""
    return make_shapefile_zip


@pytest.fixture
def kml_factory():
    """Expose the KML wrapper to API tests."""
    return make_kml
