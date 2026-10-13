"""Manifest parsing tests."""

import json
from pathlib import Path

import pytest

from roadrisk.data.errors import ManifestError
from roadrisk.data.manifest import load_manifest, parse_manifest

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_COLLISION_URL = (
    "https://data.dft.gov.uk/road-accidents-safety-data/"
    "dft-road-casualty-statistics-collision-last-5-years.csv"
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "dataset_name": "Synthetic catalog",
        "publisher": "Test",
        "catalogue_url": "https://example.test/catalog",
        "licence_name": "Test licence",
        "licence_url": "https://example.test/licence",
        "attribution": "Synthetic attribution",
        "publication_note": "Not a real dataset",
        "retrieved_on": None,
        "files": [
            {
                "id": "collisions",
                "role": "collisions",
                "filename": "synthetic.csv",
                "url": "https://example.test/synthetic.csv",
                "directory": "raw",
                "sha256": None,
                "bytes": None,
                "required": True,
                "notes": "Synthetic fixture",
            }
        ],
    }


def test_parse_manifest_accepts_null_digest() -> None:
    manifest = parse_manifest(_payload())
    assert manifest.files[0].sha256 is None
    assert manifest.files[0].directory == "raw"
    assert manifest.retrieved_on is None


def test_parse_manifest_rejects_short_digest() -> None:
    payload = _payload()
    files = payload["files"]
    assert isinstance(files, list)
    files[0]["sha256"] = "abc"
    with pytest.raises(ManifestError, match="sha256"):
        parse_manifest(payload)


def test_parse_manifest_rejects_empty_file_list() -> None:
    payload = _payload()
    payload["files"] = []
    with pytest.raises(ManifestError, match="files"):
        parse_manifest(payload)


def test_load_manifest_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="missing"):
        load_manifest(tmp_path / "absent.json")


def test_load_manifest_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ManifestError, match="JSON"):
        load_manifest(path)


def test_project_manifest_records_the_official_collision_source() -> None:
    manifest = load_manifest(ROOT / "configs" / "data_manifest.json")
    collision = manifest.file_by_id("collisions-last-5-years")
    assert manifest.licence_name == "Open Government Licence v3.0"
    assert collision.url == OFFICIAL_COLLISION_URL
    assert collision.sha256 is not None
    assert len(collision.sha256) == 64
    assert collision.byte_size == 97669586
    json.loads((ROOT / "configs" / "data_manifest.json").read_text(encoding="utf-8"))
