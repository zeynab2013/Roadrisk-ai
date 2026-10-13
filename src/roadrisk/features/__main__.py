"""Build the collision feature table.

Examples:
    python -m roadrisk.features build --manifest configs/data_manifest.json
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from roadrisk.config import load_settings
from roadrisk.data.errors import DataError
from roadrisk.data.manifest import load_manifest, resolve_path
from roadrisk.data.validate import file_status
from roadrisk.features.build import FEATURE_CSV, FEATURE_META, build_feature_table
from roadrisk.logging import configure_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run a feature command. Returns a process status code."""

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--manifest",
        type=Path,
        default=Path("configs/data_manifest.json"),
        help="Path to the dataset manifest",
    )
    common.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root used to resolve a relative data directory",
    )
    parser = argparse.ArgumentParser(prog="python -m roadrisk.features")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser(
        "build",
        parents=[common],
        help="Write a feature table from the verified collision extract",
    )
    build.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for the feature CSV and provenance JSON. Default: data/processed",
    )
    args = parser.parse_args(argv)
    settings = load_settings(project_root=args.root)
    configure_logging(settings.log_level)
    try:
        if args.command == "build":
            output_dir = args.output_dir
            if output_dir is None:
                output_dir = settings.data_dir / "processed"
            elif not output_dir.is_absolute():
                output_dir = (args.root / output_dir).resolve()
            _build(settings.data_dir, args.manifest, output_dir)
        return 0
    except DataError as exc:
        logger.error("%s", exc)
        return 1


def _build(data_dir: Path, manifest_path: Path, output_dir: Path) -> None:
    manifest = load_manifest(manifest_path)
    collisions = next((entry for entry in manifest.files if entry.role == "collisions"), None)
    if collisions is None:
        raise DataError("Manifest has no file with role collisions")
    path = resolve_path(data_dir, collisions)
    status = file_status(path, collisions)
    if status.state != "verified":
        raise DataError(
            f"{collisions.id} is {status.state}: {path}. "
            "The feature build stops when the file is missing or the SHA-256 does not match."
        )
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    provenance = build_feature_table(
        path,
        output_dir,
        source_meta={
            "dataset_name": manifest.dataset_name,
            "manifest_file_id": collisions.id,
            "filename": collisions.filename,
            "sha256": collisions.sha256,
            "byte_size": collisions.byte_size,
            "schema_version": manifest.schema_version,
        },
        generated_at=generated_at,
    )
    rows = provenance["rows"]
    assert isinstance(rows, dict)
    logger.info("Wrote %s", output_dir / FEATURE_CSV)
    logger.info("Wrote %s", output_dir / FEATURE_META)
    logger.info("Retained %s of %s rows", rows["retained"], rows["read"])


if __name__ == "__main__":
    raise SystemExit(main())
