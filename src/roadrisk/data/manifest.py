"""Load and resolve the dataset manifest."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from roadrisk.data.errors import ManifestError

_ALLOWED_DIRECTORIES = frozenset({"raw", "external", "processed"})
_SHA256_LENGTH = 64


@dataclass(frozen=True)
class ManifestFile:
    """One publisher file recorded in the manifest."""

    id: str
    role: str
    filename: str
    url: str
    directory: str
    sha256: str | None
    byte_size: int | None
    required: bool
    notes: str


@dataclass(frozen=True)
class DataManifest:
    """Catalog metadata for the selected sources."""

    schema_version: int
    dataset_name: str
    publisher: str
    catalogue_url: str
    licence_name: str
    licence_url: str
    attribution: str
    publication_note: str
    retrieved_on: str | None
    files: tuple[ManifestFile, ...]

    def file_by_id(self, file_id: str) -> ManifestFile:
        for entry in self.files:
            if entry.id == file_id:
                return entry
        raise ManifestError(f"Manifest has no file with id {file_id!r}")


def resolve_path(data_dir: Path, entry: ManifestFile) -> Path:
    """Return the local path for a manifest entry."""

    return data_dir / entry.directory / entry.filename


def load_manifest(path: Path) -> DataManifest:
    """Parse a manifest JSON file.

    Raises:
        ManifestError: The file is missing, not an object, or fails validation.
    """

    if not path.is_file():
        raise ManifestError(f"Manifest file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ManifestError("Manifest root must be a JSON object")
    return parse_manifest(payload)


def parse_manifest(payload: Mapping[str, object]) -> DataManifest:
    """Validate an already-decoded manifest object."""

    version = payload.get("schema_version")
    if version != 1:
        raise ManifestError(f"Unsupported manifest schema_version: {version!r}")
    files_raw = payload.get("files")
    if not isinstance(files_raw, list) or not files_raw:
        raise ManifestError("Manifest files must be a non-empty list")
    files = tuple(_parse_file(item) for item in files_raw)
    ids = [entry.id for entry in files]
    if len(ids) != len(set(ids)):
        raise ManifestError("Manifest file ids must be unique")
    return DataManifest(
        schema_version=1,
        dataset_name=_require_text(payload, "dataset_name"),
        publisher=_require_text(payload, "publisher"),
        catalogue_url=_require_text(payload, "catalogue_url"),
        licence_name=_require_text(payload, "licence_name"),
        licence_url=_require_text(payload, "licence_url"),
        attribution=_require_text(payload, "attribution"),
        publication_note=_require_text(payload, "publication_note"),
        retrieved_on=_optional_text(payload.get("retrieved_on")),
        files=files,
    )


def _parse_file(item: object) -> ManifestFile:
    if not isinstance(item, dict):
        raise ManifestError("Each manifest file must be a JSON object")
    directory = _require_text(item, "directory")
    if directory not in _ALLOWED_DIRECTORIES:
        raise ManifestError(f"Unsupported data directory {directory!r}")
    return ManifestFile(
        id=_require_text(item, "id"),
        role=_require_text(item, "role"),
        filename=_require_text(item, "filename"),
        url=_require_text(item, "url"),
        directory=directory,
        sha256=_optional_sha256(item.get("sha256")),
        byte_size=_optional_size(item.get("bytes")),
        required=bool(item.get("required", False)),
        notes=_optional_text(item.get("notes")) or "",
    )


def _require_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"Manifest field {key!r} must be a non-empty string")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestError("Optional text fields must be strings or null")
    stripped = value.strip()
    return stripped or None


def _optional_sha256(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH:
        raise ManifestError("sha256 must be a 64-character hex digest or null")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ManifestError("sha256 must be hexadecimal") from exc
    return value.lower()


def _optional_size(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManifestError("bytes must be a non-negative integer or null")
    return value
