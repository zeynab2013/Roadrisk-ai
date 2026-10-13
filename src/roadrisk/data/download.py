"""Download publisher files recorded in the manifest."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from roadrisk.data.errors import DataFileError, IntegrityError
from roadrisk.data.integrity import verify_sha256
from roadrisk.data.manifest import ManifestFile, resolve_path
from roadrisk.data.validate import file_status

logger = logging.getLogger(__name__)

USER_AGENT = "RoadRisk/0.1.0 (data-foundation)"
Opener = Callable[..., Any]


def download_file(
    url: str,
    destination: Path,
    *,
    opener: Opener = urlopen,
    timeout: float = 180,
) -> None:
    """Stream ``url`` to ``destination`` via a temporary ``.partial`` file.

    An existing destination is left untouched. Callers decide whether a
    file already on disk should be replaced.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=timeout) as response, temporary.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def ensure_manifest_file(
    data_dir: Path,
    entry: ManifestFile,
    *,
    opener: Opener = urlopen,
    force: bool = False,
) -> Path:
    """Download ``entry`` when it is missing, then check a recorded digest.

    A file whose digest already matches is not downloaded again. A file
    whose digest disagrees is left in place and reported as an integrity
    failure unless ``force`` is set.
    """

    destination = resolve_path(data_dir, entry)
    if destination.is_file() and not force:
        status = file_status(destination, entry)
        if status.state == "verified":
            logger.info("Already verified %s", destination.name)
            return destination
        raise DataFileError(
            f"{destination.name} is present but the manifest has no SHA-256 to check"
        )
    if destination.is_file() and force:
        destination.unlink()
    logger.info("Downloading %s", entry.url)
    download_file(entry.url, destination, opener=opener)
    if entry.sha256 is None:
        raise DataFileError(
            f"Downloaded {destination.name}, but the manifest has no SHA-256 to verify it"
        )
    verify_sha256(destination, entry.sha256)
    if entry.byte_size is not None and destination.stat().st_size != entry.byte_size:
        raise IntegrityError(
            f"Size mismatch for {destination.name}: expected {entry.byte_size} bytes, "
            f"found {destination.stat().st_size}"
        )
    return destination
