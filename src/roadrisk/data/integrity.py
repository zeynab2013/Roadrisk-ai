"""SHA-256 helpers for publisher files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from roadrisk.data.errors import DataFileError, IntegrityError


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the lowercase hex SHA-256 digest of ``path``."""

    if not path.is_file():
        raise DataFileError(f"Cannot hash a missing file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> str:
    """Return the digest when it matches ``expected``.

    Raises:
        IntegrityError: The computed digest differs from ``expected``.
    """

    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise IntegrityError(
            f"SHA-256 mismatch for {path.name}: expected {expected.lower()}, computed {actual}"
        )
    return actual
