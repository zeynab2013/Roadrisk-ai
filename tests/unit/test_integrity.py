"""SHA-256 verification tests. The payload is a standard digest vector, not road data."""

from pathlib import Path

import pytest

from roadrisk.data.errors import DataFileError, IntegrityError
from roadrisk.data.integrity import sha256_file, verify_sha256

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_matches_known_vector(tmp_path: Path) -> None:
    path = tmp_path / "vector.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == ABC_SHA256
    assert verify_sha256(path, ABC_SHA256.upper()) == ABC_SHA256


def test_sha256_mismatch_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "vector.bin"
    path.write_bytes(b"abc")
    with pytest.raises(IntegrityError, match="vector.bin"):
        verify_sha256(path, "0" * 64)


def test_sha256_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DataFileError, match="missing"):
        sha256_file(tmp_path / "absent.bin")
