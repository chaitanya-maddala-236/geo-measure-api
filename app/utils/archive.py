"""Safe validation and extraction for uploaded Shapefile ZIP archives."""

import logging
import stat
import zipfile
from pathlib import Path, PurePosixPath

from app.core.exceptions import ProcessingError

logger = logging.getLogger(__name__)
REQUIRED_SIDECARS = {".shp", ".shx", ".dbf"}
MAX_ARCHIVE_ENTRIES = 10_000


def extract_shapefile_archive(
    archive_path: Path, destination: Path, max_uncompressed_bytes: int
) -> Path:
    """Validate a ZIP and safely extract its single complete Shapefile."""
    if not zipfile.is_zipfile(archive_path):
        raise ProcessingError("The uploaded ZIP archive is corrupt or invalid.")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if not members:
                raise ProcessingError("The ZIP archive is empty.")
            if len(members) > MAX_ARCHIVE_ENTRIES:
                raise ProcessingError("The ZIP archive contains too many entries.")

            total_size = sum(member.file_size for member in members)
            if total_size > max_uncompressed_bytes:
                raise ProcessingError(
                    "The ZIP archive expands beyond the configured limit."
                )

            for member in members:
                _validate_member(member)

            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise ProcessingError("The ZIP archive failed its integrity check.")

            archive.extractall(destination)
    except ProcessingError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        logger.info("ZIP archive validation failed: %s", type(exc).__name__)
        raise ProcessingError(
            "The uploaded ZIP archive is corrupt or invalid."
        ) from exc

    shapefiles = sorted(
        path
        for path in destination.rglob("*")
        if path.is_file() and path.suffix.lower() == ".shp"
    )
    if not shapefiles:
        raise ProcessingError("The ZIP archive does not contain a Shapefile (.shp).")
    if len(shapefiles) != 1:
        raise ProcessingError("The ZIP archive must contain exactly one Shapefile.")

    shapefile = shapefiles[0]
    sibling_extensions = {
        path.suffix.lower()
        for path in shapefile.parent.iterdir()
        if path.is_file() and path.stem.casefold() == shapefile.stem.casefold()
    }
    missing = REQUIRED_SIDECARS - sibling_extensions
    if missing:
        names = ", ".join(sorted(missing))
        raise ProcessingError(
            f"The Shapefile is missing required companion files: {names}."
        )
    return shapefile


def _validate_member(member: zipfile.ZipInfo) -> None:
    """Reject ZIP members that can escape extraction or behave as symlinks."""
    raw_name = member.filename
    normalized = raw_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    mode = member.external_attr >> 16

    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or (path.parts and ":" in path.parts[0])
        or stat.S_ISLNK(mode)
    ):
        raise ProcessingError("The ZIP archive contains an unsafe file path.")
    if member.flag_bits & 0x1:
        raise ProcessingError("Encrypted ZIP archives are not supported.")
