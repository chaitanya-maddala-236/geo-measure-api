# GeoMeasure API

GeoMeasure API is a synchronous FastAPI service that accepts KML files and ZIP
archives containing one ESRI Shapefile. It extracts and persists source
features, returns their attributes and GeoJSON geometry, and calculates polygon
area or line length in meters when a safe projected CRS is available.

## Features

- Accepts `.kml` and `.zip` Shapefile uploads.
- Persists file records and extracted feature results in SQLite.
- Calculates Polygon/MultiPolygon area in square meters and
  LineString/MultiLineString length in meters.
- Marks Point/MultiPoint as `NOT_REQUIRED` and unsupported geometry as
  `UNSUPPORTED` without stopping other features.
- Transforms geographic coordinates to a local projected CRS before measuring.
- Validates ZIP integrity, companion files, extraction paths and archive size.
- Exposes interactive OpenAPI documentation at `/docs`.

## Tech stack

- **FastAPI / Pydantic** for HTTP APIs and response validation.
- **GeoPandas / Pyogrio / Shapely** for vector-file reading and geometry work.
- **PyProj** for CRS inspection and coordinate transformation.
- **SQLAlchemy / SQLite** for persistence.
- **Pytest / HTTPX / Ruff / Black** for tests and code quality.

## Architecture

```text
app/
├── main.py                 # Application factory, lifespan and error handler
├── api/files.py            # HTTP routes
├── core/                   # Settings, exceptions and logging
├── db/                     # SQLAlchemy engine and models
├── schemas/files.py        # Response contracts
├── services/
│   ├── file_service.py     # Upload orchestration and persistence
│   ├── geospatial_service.py # KML and Shapefile parsing
│   ├── crs_service.py      # Measurement CRS selection
│   └── measurement_service.py # Per-feature measurement outcomes
└── utils/                  # ZIP validation and JSON normalization
```

Routes handle HTTP input and output. Services implement file processing and
measurements. SQLAlchemy models define persistence, and Pydantic schemas define
the public response format. SQLite tables are initialized from SQLAlchemy
metadata at application startup; Alembic migrations are not needed for this
small initial version and can be added when schema evolution is required.

## Processing flow

```text
Upload
→ Extension and size validation
→ ZIP integrity, path and companion-file validation (when applicable)
→ GeoPandas parsing
→ Feature, geometry and property extraction
→ Source CRS inspection and projected CRS selection
→ Measurement calculation per feature
→ SQLite persistence
→ API response
```

Uploads are copied in bounded chunks to a temporary directory. ZIP contents are
checked for traversal paths, symlinks, encryption, CRC failures and total
uncompressed size before extraction. The temporary directory is removed after
processing. One file record is created for accepted extensions; a parser or
archive failure is returned as a `FAILED` processing record with a safe error
message.

Feature geometry is stored once as GeoJSON in the feature row along with its
properties and measurement. This keeps measurement responses available after
the temporary upload is removed. Files use UUID-style public IDs; feature
database keys remain internal.

## CRS strategy

Area and length are never calculated on geographic longitude/latitude values.
For a projected source CRS whose coordinate units are meters, GeoMeasure uses
that CRS. For a geographic CRS, or a projected CRS whose axes are not meters,
the service transforms the dataset extent to geographic coordinates and selects
the UTM zone containing the combined feature centroid. EPSG:326xx is selected
in the northern hemisphere and EPSG:327xx in the southern hemisphere. At
latitudes north of 84° or south of 80°, the corresponding WGS 84 UPS polar
stereographic CRS is selected.

This produces meter-based coordinates before calculating polygon area or line
length. EPSG:4326 uses angular degrees, whose areas and distances vary with
latitude, so degree-based calculations would not represent square meters or
meters. If CRS metadata is missing, features are still retained, but measurable
features receive `ERROR` and a null measurement. The service does not guess a
CRS.

UTM works best for local datasets within or near one zone. A single centroid-
based projection can introduce material distortion for data spanning multiple
zones, crossing the antimeridian, or covering a large region. Meter-based
projected input is trusted as supplied, so distortion inherent in projections
such as Web Mercator is not corrected. Global or legal-grade measurements may
need a geodesic calculation or a domain-specific equal-area projection.

## Setup

Requires Python 3.11 or newer. GeoPandas/Pyogrio wheels provide their GDAL
runtime for local Python installs; the Docker image also installs system GDAL,
PROJ and GEOS packages.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS / Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

The service uses `sqlite:///./geo_measure.db` by default. Settings can be
changed in `.env` or as environment variables:

| Setting | Default | Purpose |
| --- | ---: | --- |
| `DATABASE_URL` | `sqlite:///./geo_measure.db` | SQLAlchemy database URL |
| `MAX_UPLOAD_SIZE_BYTES` | `52428800` (50 MiB) | Maximum uploaded file size |
| `MAX_ARCHIVE_UNCOMPRESSED_BYTES` | `209715200` (200 MiB) | Maximum ZIP expanded size |
| `LOG_LEVEL` | `INFO` | Application log level |

## Run

```bash
uvicorn app.main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for Swagger UI.

## Docker

```bash
docker compose up --build
```

The API listens on port 8000 and persists SQLite data in the named
`geomeasure_data` volume. Set `MAX_UPLOAD_SIZE_BYTES`,
`MAX_ARCHIVE_UNCOMPRESSED_BYTES` or `LOG_LEVEL` in the environment before
starting Compose to override the defaults.

## API

### `POST /api/files/`

Multipart form field `upload` accepts a `.kml` file or `.zip` containing exactly
one Shapefile. Accepted uploads return HTTP 201 and a file record. A file that
was accepted by extension but fails parsing is also recorded with `status` set
to `FAILED` and an `error_message`. Unsupported extensions return 415; empty or
oversized uploads return 400 or 413.

```bash
curl -F "upload=@survey.kml" http://localhost:8000/api/files/
```

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

### `GET /api/files/{id}/`

Returns the same file metadata record. Unknown IDs return HTTP 404.

```bash
curl http://localhost:8000/api/files/8fb253821e75453598cda6a70bdbef0e/
```

### `GET /api/files/{id}/measurements/`

Returns one entry per feature, including its source CRS, GeoJSON geometry,
properties, measurement status and optional measurement CRS.

```bash
curl http://localhost:8000/api/files/8fb253821e75453598cda6a70bdbef0e/measurements/
```

Example response:

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
      "geometry": {"type": "Polygon", "coordinates": [[[78.0, 17.0], [78.001, 17.0], [78.001, 17.001], [78.0, 17.0]]]},
      "crs": "EPSG:4326",
      "properties": {"name": "parcel"},
      "measurement": 11700.5,
      "measurement_type": "area",
      "measurement_unit": "m²",
      "measurement_status": "CALCULATED",
      "measurement_crs": "EPSG:32644",
      "measurement_error": null
    }
  ]
}
```

Measurement statuses are `CALCULATED`, `NOT_REQUIRED`, `UNSUPPORTED` and
`ERROR`. A measurement error is returned per feature and does not discard other
features.

### `GET /health`

Returns `{"status":"ok"}` as a simple liveness check.

## Testing and code quality

```bash
pytest
ruff check app tests
black --check app tests
```

Tests construct small KML and Shapefile fixtures locally and do not call
external services.

## Design decisions

- **Synchronous processing:** GeoPandas parsing is CPU- and I/O-heavy, but
  processing is kept in-process to keep the first version operationally simple.
  Large files can later move to a background worker.
- **SQLite and SQLAlchemy:** one local database makes setup straightforward.
  PostgreSQL/PostGIS is a better fit for multi-user concurrency and spatial
  querying at scale.
- **GeoJSON feature persistence:** geometry and properties are stored per
  feature so a measurement request remains available after temporary upload
  cleanup. The source file itself is not retained.
- **Per-feature outcomes:** unsupported geometries, points, and measurement
  failures have explicit statuses so one problematic feature does not abort the
  rest of a valid file.
- **Schema initialization:** SQLAlchemy `create_all` is sufficient for this
  initial schema; Alembic migrations should be introduced before evolving a
  deployed database.

## Limitations

- Requests are processed synchronously; there is no progress tracking or retry
  queue.
- Uploads are limited to 50 MiB by default and ZIP expansion to 200 MiB.
- UTM selection assumes the dataset is local to one zone; large, polar, or
  antimeridian-crossing extents need more specialized measurement methods.
- SQLite is intended for local/small deployments, not high-write concurrency.
- Geometry and properties are returned together for all features; very large
  responses need pagination or streaming.
- The original uploaded file is discarded after processing.

## Learning

This project applies the distinction between geographic coordinates measured
in angular degrees and projected coordinates measured in linear units. It also
shows how GeoPandas, Shapely and PyProj fit into a backend processing pipeline,
how geometry types need different measurement handling, and how to isolate
file parsing, CRS logic, persistence and HTTP contracts into maintainable
layers.

## Future scope

- Add a background worker and processing progress/status updates.
- Store data in PostGIS and add geometry-aware querying.
- Move source uploads and large derived artifacts to object storage.
- Add measurement pagination and output formats for large datasets.
- Add authentication, quotas and per-user retention policies.
- Offer geodesic calculations and configurable equal-area projections.
- Add structured metrics, tracing, monitoring and cloud deployment support.
