"""ZIP archive path validation tests."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.core.exceptions import ProcessingError
from app.utils.archive import extract_shapefile_archive


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("../escape.shp", "not a real shapefile")
    with pytest.raises(ProcessingError, match="unsafe file path"):
        extract_shapefile_archive(archive_path, tmp_path / "out", 10_000)


def test_expansion_limit_is_enforced(tmp_path: Path) -> None:
    archive_path = tmp_path / "large.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("large.txt", "x" * 1024)
    with pytest.raises(ProcessingError, match="configured limit"):
        extract_shapefile_archive(archive_path, tmp_path / "out", 20)
