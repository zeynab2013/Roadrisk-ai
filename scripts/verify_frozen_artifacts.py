#!/usr/bin/env python3
"""Check frozen artifact bytes against docs/artifact-manifest.json.

The script reads files and prints hashes. It does not load joblib, score rows,
or write, copy, download, or delete anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "artifact-manifest.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Directory that contains the artifact paths")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Tracked artifact manifest")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest_path = args.manifest.resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"manifest unreadable: {exc}", file=sys.stderr)
        return 1
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        print("manifest has no artifacts", file=sys.stderr)
        return 1
    failed = False
    for item in artifacts:
        if not isinstance(item, dict):
            print("manifest entry is not an object", file=sys.stderr)
            failed = True
            continue
        failed = _check(root, item) or failed
    return 1 if failed else 0


def _check(root: Path, item: dict[str, object]) -> bool:
    relative = item.get("path")
    expected = item.get("sha256")
    required = bool(item.get("required"))
    if not isinstance(relative, str) or not isinstance(expected, str):
        print("manifest entry is missing path or sha256", file=sys.stderr)
        return True
    path = _inside(root, relative)
    if path is None:
        print(f"rejected {relative}", file=sys.stderr)
        print(f"expected {expected}", file=sys.stderr)
        return True
    if not path.is_file():
        label = "missing" if required else "optional-missing"
        print(f"{label} {relative}")
        print(f"expected {expected}")
        print("actual   absent")
        return required
    actual = _sha256(path)
    if actual != expected:
        print(f"mismatch {relative}")
        print(f"expected {expected}")
        print(f"actual   {actual}")
        return True
    print(f"ok {relative}")
    return False


def _inside(root: Path, relative: str) -> Path | None:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    path = (root / candidate).resolve()
    if path != root and root not in path.parents:
        return None
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
