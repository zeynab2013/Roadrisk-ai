"""Command line for the data catalog.

Examples:
    python -m roadrisk.data verify --manifest configs/data_manifest.json
    python -m roadrisk.data download --manifest configs/data_manifest.json
    python -m roadrisk.data audit --manifest configs/data_manifest.json
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from roadrisk.config import load_settings
from roadrisk.data.download import ensure_manifest_file
from roadrisk.data.errors import DataError
from roadrisk.data.manifest import DataManifest, load_manifest, resolve_path
from roadrisk.data.quality import assert_output_dir_is_safe, audit_csv
from roadrisk.data.report import write_audit
from roadrisk.data.validate import file_status, inspect_csv
from roadrisk.logging import configure_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run a data-catalog command. Returns a process status code."""

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
    parser = argparse.ArgumentParser(prog="python -m roadrisk.data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser(
        "verify",
        parents=[common],
        help="Check required files against the manifest",
    )
    verify.add_argument(
        "--inspect-header",
        action="store_true",
        help="Also validate the header of each collisions CSV",
    )
    subparsers.add_parser(
        "download",
        parents=[common],
        help="Download required files that are not already verified",
    )
    audit = subparsers.add_parser(
        "audit",
        parents=[common],
        help="Write a data-quality audit for the verified collision extract",
    )
    audit.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/quality"),
        help="Directory for the JSON and Markdown audit",
    )

    args = parser.parse_args(argv)
    settings = load_settings(project_root=args.root)
    configure_logging(settings.log_level)
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "verify":
            _verify(settings.data_dir, manifest, inspect_header=args.inspect_header)
        elif args.command == "download":
            for entry in manifest.files:
                if entry.required:
                    ensure_manifest_file(settings.data_dir, entry)
        else:
            output_dir = args.output_dir
            if not output_dir.is_absolute():
                output_dir = (args.root / output_dir).resolve()
            _audit(settings.data_dir, manifest, output_dir=output_dir)
        return 0
    except DataError as exc:
        logger.error("%s", exc)
        return 1


def _verify(data_dir: Path, manifest: DataManifest, *, inspect_header: bool) -> None:
    for entry in manifest.files:
        if not entry.required:
            continue
        path = resolve_path(data_dir, entry)
        status = file_status(path, entry)
        if status.state != "verified":
            raise DataError(
                f"{entry.id} is {status.state}: {path}. "
                "A required file must exist and match the recorded SHA-256."
            )
        logger.info("Verified %s", path.name)
        if inspect_header and entry.role == "collisions":
            report = inspect_csv(path)
            logger.info(
                "Header ok for %s (%s columns)",
                path.name,
                len(report.header.columns),
            )


def _audit(data_dir: Path, manifest: DataManifest, *, output_dir: Path) -> None:
    collisions = next((entry for entry in manifest.files if entry.role == "collisions"), None)
    if collisions is None:
        raise DataError("Manifest has no file with role collisions")
    path = resolve_path(data_dir, collisions)
    assert_output_dir_is_safe(output_dir, path)
    status = file_status(path, collisions)
    if status.state != "verified":
        raise DataError(
            f"{collisions.id} is {status.state}: {path}. "
            "The audit stops when the collision file is missing or the SHA-256 does not match."
        )
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = audit_csv(
        path,
        source={
            "dataset_name": manifest.dataset_name,
            "manifest_file_id": collisions.id,
            "filename": collisions.filename,
            "sha256": collisions.sha256,
            "byte_size": collisions.byte_size,
            "schema_version": manifest.schema_version,
            "catalogue_url": manifest.catalogue_url,
        },
        generated_at=generated_at,
    )
    json_path, markdown_path = write_audit(report, output_dir)
    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", markdown_path)


if __name__ == "__main__":
    raise SystemExit(main())
