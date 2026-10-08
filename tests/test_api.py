"""HTTP contract, upload validation and persistence tests."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_kml_upload_and_mixed_geometry_features(
    client: TestClient, kml_factory
) -> None:
    route = (
        "<Placemark><name>route</name><LineString><coordinates>"
        "78,17 78.001,17</coordinates></LineString></Placemark>"
    )
    polygon = (
        "<Placemark><name>site</name><Polygon><outerBoundaryIs><LinearRing>"
        "<coordinates>78,17 78.001,17 78.001,17.001 78,17.001 78,17"
        "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
    )
    point = (
        "<Placemark><name>marker</name><Point><coordinates>"
        "78,17</coordinates></Point></Placemark>"
    )
    content = kml_factory(route, polygon, point)
    response = client.post("/api/files/", files={"upload": ("survey.kml", content)})
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "survey.kml"
    assert data["file_type"] == "KML"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 3
    assert data["source_crs"] is not None
    assert len(data["id"]) == 32

    measured = client.get(f"/api/files/{data['id']}/measurements/")
    assert measured.status_code == 200
    features = measured.json()["features"]
    assert {item["geometry_type"] for item in features} == {
        "LineString",
        "Polygon",
        "Point",
    }
    assert {item["measurement_status"] for item in features} == {
        "CALCULATED",
        "NOT_REQUIRED",
    }
    assert all(item["geometry"] is not None for item in features)


def test_shapefile_zip_upload_and_info(
    client: TestClient, shapefile_zip_factory, tmp_path: Path
) -> None:
    content = shapefile_zip_factory(tmp_path)
    response = client.post("/api/files/", files={"upload": ("parcel.zip", content)})
    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "COMPLETED"
    assert created["file_type"] == "SHAPEFILE_ZIP"
    assert created["feature_count"] == 1

    info = client.get(f"/api/files/{created['id']}/")
    assert info.status_code == 200
    assert info.json() == created

    measured = client.get(f"/api/files/{created['id']}/measurements/").json()
    assert measured["features"][0]["properties"]["name"] == "test parcel"
    assert measured["features"][0]["measurement_unit"] == "m²"


def test_api_response_contains_validated_measurement_fields(
    client: TestClient, kml_factory
) -> None:
    content = kml_factory(
        "<Placemark><Point><coordinates>78,17</coordinates></Point></Placemark>"
    )
    created = client.post(
        "/api/files/", files={"upload": ("point.kml", content)}
    ).json()
    result = client.get(f"/api/files/{created['id']}/measurements/").json()
    feature = result["features"][0]
    assert feature["measurement_status"] == "NOT_REQUIRED"
    assert feature["measurement"] is None
    assert feature["crs"] == result["source_crs"]
    assert feature["properties"] is not None


def test_missing_file_id_returns_clean_404(client: TestClient) -> None:
    response = client.get("/api/files/not-a-real-id/")
    assert response.status_code == 404
    assert response.json() == {"detail": "File not found."}


def test_measurements_for_missing_file_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/files/not-a-real-id/measurements/")
    assert response.status_code == 404


def test_unsupported_extension_returns_415(client: TestClient) -> None:
    response = client.post("/api/files/", files={"upload": ("data.geojson", b"{}")})
    assert response.status_code == 415
    assert "Only .kml and .zip" in response.json()["detail"]


def test_corrupt_zip_is_persisted_as_failed(client: TestClient) -> None:
    response = client.post(
        "/api/files/", files={"upload": ("broken.zip", b"not a zip")}
    )
    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert "corrupt" in response.json()["error_message"]


def test_invalid_kml_is_persisted_as_failed(client: TestClient) -> None:
    response = client.post("/api/files/", files={"upload": ("broken.kml", b"<kml")})
    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert response.json()["error_message"] == "The KML file could not be read."


def test_zip_without_shapefile_is_failed(client: TestClient, tmp_path: Path) -> None:
    archive_path = tmp_path / "notes.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("readme.txt", "no vector data")
    response = client.post(
        "/api/files/", files={"upload": ("notes.zip", archive_path.read_bytes())}
    )
    assert response.json()["status"] == "FAILED"
    assert "does not contain a Shapefile" in response.json()["error_message"]


def test_missing_shapefile_companions_are_reported(
    client: TestClient, shapefile_zip_factory, tmp_path: Path
) -> None:
    content = shapefile_zip_factory(tmp_path, omit={".dbf"})
    response = client.post("/api/files/", files={"upload": ("incomplete.zip", content)})
    assert response.json()["status"] == "FAILED"
    assert ".dbf" in response.json()["error_message"]


def test_missing_source_crs_keeps_features_and_marks_measurement_error(
    client: TestClient, shapefile_zip_factory, tmp_path: Path
) -> None:
    with pytest.warns(UserWarning, match="'crs' was not provided"):
        content = shapefile_zip_factory(tmp_path, include_projection=False)
    response = client.post("/api/files/", files={"upload": ("no-crs.zip", content)})
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["source_crs"] is None
    assert "CRS is missing" in data["error_message"]
    measured = client.get(f"/api/files/{data['id']}/measurements/").json()
    assert measured["features"][0]["measurement_status"] == "ERROR"
    assert measured["features"][0]["measurement"] is None


def test_upload_size_limit_is_enforced(tmp_path: Path) -> None:
    from app.core.config import Settings
    from app.main import create_app

    database_path = (tmp_path / "limited.db").as_posix()
    app = create_app(
        Settings(database_url=f"sqlite:///{database_path}", max_upload_size_bytes=8)
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/files/", files={"upload": ("large.kml", b"123456789")}
        )
    assert response.status_code == 413
