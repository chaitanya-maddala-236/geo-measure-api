# GeoMeasure API

GeoMeasure is a FastAPI service for uploading KML files and ZIP archives that
contain an ESRI Shapefile. It extracts feature geometry and attributes, stores
the results in SQLite, and calculates polygon area or line length in meters
when the source CRS supports a safe projected measurement.

## What it supports

- `.kml` files and `.zip` archives containing exactly one Shapefile.
- Polygon and MultiPolygon area in square meters (`m²`).
- LineString and MultiLineString length in meters (`m`).
- Point and MultiPoint features with status `NOT_REQUIRED`.
- Other geometry types retained with status `UNSUPPORTED`.
- Geographic and non-meter CRS transformation before measurement.
- Per-feature measurement errors, so an unmeasurable feature does not discard
  the other features in the file.
- Bounded uploads and ZIP validation for unsafe paths, symlinks, encrypted
  members, corrupt archives, too many entries, and oversized extraction.

## Quick start with Docker

Prerequisite: Docker Desktop or Docker Engine with Docker Compose.

```bash
git clone https://github.com/chaitanya-maddala-236/geo-measure-api.git
cd geo-measure-api
docker compose up --build
```

The API listens on [http://127.0.0.1:8000](http://127.0.0.1:8000). Open
[Swagger UI](http://127.0.0.1:8000/docs) to try the endpoints, or check
[the health endpoint](http://127.0.0.1:8000/health). Docker Compose stores the
SQLite database in the named `geomeasure_data` volume. Stop the service with
`Ctrl+C`; use `docker compose down` to remove the container and network while
keeping the database volume.

## Run locally with Python

Requires Python 3.11 or newer. GeoPandas and Pyogrio install their supported
binary wheels for common platforms. Docker is recommended when the local system
does not have compatible GDAL/PROJ libraries.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API docs are at
`/docs`. The development requirements include the test client, pytest, Ruff
and Black. The Docker image installs only `requirements.txt`, which contains
runtime dependencies.

## Configuration

Settings can be supplied in `.env` or as environment variables. Environment
variables take precedence.

| Setting | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./geo_measure.db` | SQLAlchemy database URL |
| `MAX_UPLOAD_SIZE_BYTES` | `52428800` (50 MiB) | Maximum compressed upload size |
| `MAX_ARCHIVE_UNCOMPRESSED_BYTES` | `209715200` (200 MiB) | Maximum total ZIP expansion size |
| `LOG_LEVEL` | `INFO` | Python logging level |

The original uploaded file is temporary and is deleted after processing. File
metadata, extracted geometries, properties, and measurement results remain in
the configured database.

## API

All upload requests use `multipart/form-data` with a file field named `upload`.

### `POST /api/files/`

Upload a `.kml` or `.zip` Shapefile archive. A valid upload returns HTTP `201`
with its processing record. A file that passes upload validation but cannot be
parsed is still recorded with status `FAILED` and an `error_message`.

```bash
curl -F "upload=@survey.kml" http://127.0.0.1:8000/api/files/
```

PowerShell can use `curl.exe` with the same form field:

```powershell
curl.exe -F "upload=@survey.kml" http://127.0.0.1:8000/api/files/
```

For a Shapefile, upload a ZIP containing the `.shp`, `.shx`, and `.dbf`
components with matching names. A `.prj` file is recommended to provide CRS
metadata. Without a CRS, features are retained but polygon and line measurements
are marked `ERROR` rather than guessed.

Example response:

```json
{
  "id": "8fb253821e75453598cda6a70bdbef0e",
  "filename": "survey.kml",
  "file_type": "KML",
  "feature_count": 2,
  "source_crs": "EPSG:4326",
  "status": "COMPLETED",
  "created_at": "2026-01-01T12:00:00Z",
  "updated_at": "2026-01-01T12:00:01Z",
  "error_message": null
}
```

Common upload errors include HTTP `415` for unsupported extensions, `400` for
an empty upload, and `413` when the upload exceeds its configured size limit.
Expected parse and archive errors return a file record with status `FAILED`.

### `GET /api/files/{id}/`

Return the metadata and processing status for one upload. An unknown ID returns
HTTP `404`.

```bash
curl http://127.0.0.1:8000/api/files/8fb253821e75453598cda6a70bdbef0e/
```

### `GET /api/files/{id}/measurements/`

Return every feature's source GeoJSON geometry, CRS, properties, and measurement
outcome. Measurements are calculated in a projected CRS with meter units.

```bash
curl http://127.0.0.1:8000/api/files/8fb253821e75453598cda6a70bdbef0e/measurements/
```

Example response (shortened to one feature):

```json
{
  "file_id": "8fb253821e75453598cda6a70bdbef0e",
  "filename": "survey.kml",
  "feature_count": 1,
  "source_crs": "EPSG:4326",
  "status": "COMPLETED",
  "features": [
    {
      "feature_index": 0,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[78.0, 17.0], [78.001, 17.0], [78.001, 17.001], [78.0, 17.0]]]
      },
      "crs": "EPSG:4326",
      "properties": {"name": "parcel"},
      "measurement": 5902.5,
      "measurement_type": "area",
      "measurement_unit": "m²",
      "measurement_status": "CALCULATED",
      "measurement_crs": "EPSG:32644",
      "measurement_error": null
    }
  ]
}
```

`measurement_status` is one of:

| Status | Meaning |
| --- | --- |
| `CALCULATED` | A measurement was calculated successfully. |
| `NOT_REQUIRED` | Point and MultiPoint geometries do not need a measurement. |
| `UNSUPPORTED` | The geometry type is retained but has no measurement implementation. |
| `ERROR` | A supported geometry could not be measured safely, for example because its CRS is missing. |

### `GET /health`

Return `{"status":"ok"}` as a simple liveness check.

## Architecture and processing

```text
app/
├── main.py                    # App factory, lifespan and error handler
├── api/files.py               # HTTP routes
├── core/                      # Settings, exceptions and logging
├── db/                        # SQLAlchemy engine and models
├── schemas/files.py           # Validated API response schemas
├── services/
│   ├── file_service.py        # Upload orchestration and persistence
│   ├── geospatial_service.py  # KML and Shapefile parsing
│   ├── crs_service.py         # Measurement CRS selection
│   └── measurement_service.py # Per-feature measurement outcomes
└── utils/                     # ZIP validation and JSON normalization
```

The upload endpoint validates the extension and streams the body to a temporary
file in bounded chunks. ZIP archives are checked before extraction. GeoPandas
and Pyogrio read the KML or Shapefile, after which each feature's geometry and
properties are normalized and stored with its measurement result. The file
record and features are persisted in SQLite; the temporary directory is then
removed. File IDs are UUID-style strings, while feature indexes preserve source
order.

## CRS and measurement approach

The service does not calculate planar area or length directly from geographic
longitude and latitude. If the source CRS is projected and its coordinate units
are meters, that CRS is used. Otherwise, geometries are transformed to
geographic coordinates, the combined feature extent's centroid selects a local
UTM zone, and polar datasets use WGS 84 UPS. The geometries are transformed to
that measurement CRS before Shapely calculates area or length.

UTM is suitable for local datasets near one zone. Centroid-based selection can
distort measurements for datasets spanning multiple zones, crossing the
antimeridian, or covering a large region. A meter-based projected source CRS is
trusted as supplied, so distortion in a projection such as Web Mercator is not
corrected. Global or legal-grade measurements may need geodesic calculations
or a domain-specific equal-area projection. Missing CRS metadata is never
guessed.

## Design decisions and trade-offs

- **Synchronous processing:** keeps deployment simple for this initial service;
  large files would be better handled by a background worker with progress and
  retry support.
- **SQLite:** makes local setup self-contained. PostgreSQL/PostGIS is a better
  choice for multi-user concurrency and spatial queries at scale.
- **Persist extracted results, not source uploads:** the measurement endpoint
  works after temporary-file cleanup while avoiding retention of uploaded
  source files.
- **Per-feature statuses:** point, unsupported, and failed measurements are
  represented explicitly so one feature does not abort a valid dataset.
- **Schema setup at startup:** SQLAlchemy creates the initial tables. Alembic
  migrations should be added before evolving a deployed schema.
- **Projected planar measurement:** provides straightforward meter-based area
  and length, with the CRS limitations described above. Geodesic or
  domain-specific calculations remain future options.

## Development and tests

Install `requirements-dev.txt`, then run:

```bash
pytest
ruff check app tests
black --check app tests
```

Tests create small KML and Shapefile fixtures locally. They cover API uploads
and responses, measurement and CRS behavior, missing or unsupported data,
invalid archives, ZIP traversal protection, and configured size limits. They do
not call external services.

## Learning

This project demonstrates why geographic coordinates in angular degrees cannot
be used directly for metric area and distance calculations. It also shows how
GeoPandas, Shapely, PyProj, FastAPI, and SQLAlchemy can be composed into a
feature-processing pipeline, and how to keep CRS selection, parsing,
measurement, persistence, and HTTP contracts in separate layers.

## Limitations and future scope

- Processing is synchronous; there is no job queue, progress endpoint, or
  retry workflow.
- Default upload and ZIP expansion limits are 50 MiB and 200 MiB.
- Large measurement responses are not paginated or streamed.
- SQLite is intended for local and small deployments, not high-write
  concurrency.
- Authentication, per-user quotas, and retention policies are not included.
- The original uploaded source file is not retained.

Possible next steps include background workers, PostGIS, object storage,
measurement pagination, configurable geodesic/equal-area methods,
authentication, observability, and cloud deployment.
