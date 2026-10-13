"""Inspect collision CSV files and report whether catalog files are present."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from roadrisk.data.errors import DataFileError, IntegrityError, SchemaError
from roadrisk.data.integrity import verify_sha256
from roadrisk.data.manifest import ManifestFile, resolve_path
from roadrisk.data.schema import ID_COLUMN, HeaderReport, require_valid_header


@dataclass(frozen=True)
class FileStatus:
    """Presence of one manifest file on disk."""

    file_id: str
    state: str
    path: Path


@dataclass(frozen=True)
class CsvInspection:
    """Header validation plus an optional row count."""

    path: Path
    byte_size: int
    header: HeaderReport
    data_rows: int | None


def file_status(path: Path, entry: ManifestFile) -> FileStatus:
    """Classify a manifest file as missing, unverified, or verified.

    A digest of null means the file cannot be called verified, even when
    bytes are present. Size and digest mismatches raise ``IntegrityError``.
    """

    if not path.is_file():
        return FileStatus(file_id=entry.id, state="missing", path=path)
    if entry.sha256 is None:
        return FileStatus(file_id=entry.id, state="unverified", path=path)
    verify_sha256(path, entry.sha256)
    if entry.byte_size is not None and path.stat().st_size != entry.byte_size:
        raise IntegrityError(
            f"Size mismatch for {path.name}: expected {entry.byte_size} bytes, "
            f"found {path.stat().st_size}"
        )
    return FileStatus(file_id=entry.id, state="verified", path=path)


def read_header(path: Path) -> list[str]:
    """Read the first CSV row.

    Raises:
        DataFileError: The path is missing, empty, or has no header row.
    """

    if not path.is_file():
        raise DataFileError(f"Required file is missing: {path}")
    if path.stat().st_size == 0:
        raise DataFileError(f"File is empty: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise DataFileError(f"File has no header row: {path}") from exc
    if not any(column.strip() for column in header):
        raise DataFileError(f"Header row is blank: {path}")
    return header


def inspect_csv(path: Path, *, count_rows: bool = False) -> CsvInspection:
    """Validate the collision header and optionally count data rows."""

    header = require_valid_header(read_header(path))
    rows = _count_rows(path) if count_rows else None
    return CsvInspection(
        path=path,
        byte_size=path.stat().st_size,
        header=header,
        data_rows=rows,
    )


def find_duplicate_ids(path: Path, *, id_column: str = ID_COLUMN) -> tuple[str, ...]:
    """Return repeated values of ``id_column``.

    The header must already satisfy the collision contract. An empty file
    body returns an empty tuple. This function does not drop or rewrite rows.
    """

    require_valid_header(read_header(path))
    seen: set[str] = set()
    duplicates: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or id_column not in reader.fieldnames:
            raise SchemaError(f"Missing required columns: {id_column}")
        for row in reader:
            value = (row.get(id_column) or "").strip()
            if not value:
                raise DataFileError(f"Blank {id_column} in {path.name}")
            if value in seen:
                duplicates.append(value)
            else:
                seen.add(value)
    return tuple(duplicates)


def require_unique_ids(path: Path, *, id_column: str = ID_COLUMN) -> None:
    """Raise ``DataFileError`` when ``id_column`` repeats."""

    duplicates = find_duplicate_ids(path, id_column=id_column)
    if duplicates:
        preview = ", ".join(duplicates[:5])
        raise DataFileError(
            f"Duplicate {id_column} values in {path.name}: {preview}"
        )


def _count_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def iter_statuses(data_dir: Path, files: Iterable[ManifestFile]) -> tuple[FileStatus, ...]:
    """Resolve each entry under ``data_dir`` and classify it."""

    return tuple(file_status(resolve_path(data_dir, entry), entry) for entry in files)
