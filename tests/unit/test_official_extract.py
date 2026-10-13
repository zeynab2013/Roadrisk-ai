"""Optional check of the local official extract.

The file is gitignored. This test skips when the extract has not been
downloaded, so the default suite does not fetch it.
"""

from pathlib import Path

import pytest

from roadrisk.data.manifest import load_manifest, resolve_path
from roadrisk.data.validate import file_status

ROOT = Path(__file__).resolve().parents[2]


def test_local_official_files_match_the_manifest() -> None:
    manifest = load_manifest(ROOT / "configs" / "data_manifest.json")
    data_dir = ROOT / "data"
    missing = [
        entry.id
        for entry in manifest.files
        if entry.required and not resolve_path(data_dir, entry).is_file()
    ]
    if missing:
        pytest.skip("Official files are not on disk: " + ", ".join(missing))
    for entry in manifest.files:
        if entry.required:
            status = file_status(resolve_path(data_dir, entry), entry)
            assert status.state == "verified"
