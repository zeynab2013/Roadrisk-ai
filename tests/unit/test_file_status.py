"""File status tests. They do not read the official extract."""

import json
from pathlib import Path

import pytest

from roadrisk.data.__main__ import main
from roadrisk.data.download import download_file, ensure_manifest_file
from roadrisk.data.errors import DataError, DataFileError, IntegrityError
from roadrisk.data.manifest import ManifestFile, parse_manifest
from roadrisk.data.validate import file_status, iter_statuses

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _entry(**overrides: object) -> ManifestFile:
    payload: dict[str, object] = {
        "id": "sample",
        "role": "collisions",
        "filename": "sample.bin",
        "url": "https://example.test/sample.bin",
        "directory": "raw",
        "sha256": ABC_SHA256,
        "bytes": 3,
        "required": True,
        "notes": "Synthetic",
    }
    payload.update(overrides)
    manifest = parse_manifest(
        {
            "schema_version": 1,
            "dataset_name": "Synthetic catalog",
            "publisher": "Test",
            "catalogue_url": "https://example.test/catalog",
            "licence_name": "Test licence",
            "licence_url": "https://example.test/licence",
            "attribution": "Synthetic",
            "publication_note": "Not a real dataset",
            "retrieved_on": None,
            "files": [payload],
        }
    )
    return manifest.files[0]


def test_missing_file_status_is_missing(tmp_path: Path) -> None:
    entry = _entry()
    status = file_status(tmp_path / "sample.bin", entry)
    assert status.state == "missing"


def test_file_without_digest_is_unverified(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    status = file_status(path, _entry(sha256=None, bytes=None))
    assert status.state == "unverified"


def test_matching_file_is_verified(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    assert file_status(path, _entry()).state == "verified"


def test_size_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    with pytest.raises(IntegrityError, match="Size mismatch"):
        file_status(path, _entry(bytes=4))


def test_empty_catalog_directory_reports_every_file_missing(tmp_path: Path) -> None:
    entry = _entry()
    statuses = iter_statuses(tmp_path, [entry])
    assert statuses[0].state == "missing"
    assert statuses[0].path == tmp_path / "raw" / "sample.bin"


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        if size < 0:
            size = len(self._payload)
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_download_then_verify(tmp_path: Path) -> None:
    def opener(_request: object, timeout: float = 0) -> _Body:
        assert timeout > 0
        return _Body(b"abc")

    destination = tmp_path / "raw" / "sample.bin"
    download_file("https://example.test/sample.bin", destination, opener=opener)
    path = ensure_manifest_file(tmp_path, _entry(), opener=opener)
    assert path.read_bytes() == b"abc"
    assert file_status(path, _entry()).state == "verified"


def test_download_refuses_unrecorded_digest(tmp_path: Path) -> None:
    destination = tmp_path / "raw" / "sample.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"abc")
    with pytest.raises(DataFileError, match="no SHA-256"):
        ensure_manifest_file(tmp_path, _entry(sha256=None, bytes=None))


def _write_manifest(path: Path, *, role: str, sha256: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_name": "Synthetic catalog",
                "publisher": "Test",
                "catalogue_url": "https://example.test/catalog",
                "licence_name": "Test licence",
                "licence_url": "https://example.test/licence",
                "attribution": "Synthetic",
                "publication_note": "Not a real dataset",
                "retrieved_on": None,
                "files": [
                    {
                        "id": "sample",
                        "role": role,
                        "filename": "sample.bin",
                        "url": "https://example.test/sample.bin",
                        "directory": "raw",
                        "sha256": sha256,
                        "bytes": 3,
                        "required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_verify_command_fails_when_required_file_is_missing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, role="collisions", sha256=ABC_SHA256)
    assert main(["verify", "--manifest", str(manifest_path), "--root", str(tmp_path)]) == 1


def test_verify_command_accepts_a_matching_synthetic_file(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "raw" / "sample.bin"
    data_file.parent.mkdir(parents=True)
    data_file.write_bytes(b"abc")
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, role="other", sha256=ABC_SHA256)
    code = main(["verify", "--manifest", str(manifest_path), "--root", str(tmp_path)])
    assert code == 0


def test_checksum_mismatch_raises(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abd")
    with pytest.raises(IntegrityError, match="SHA-256"):
        file_status(path, _entry())
    with pytest.raises(DataError):
        file_status(path, _entry())
