"""Build a feature table from a verified collision extract.

The writer does not modify the source file and does not fit an encoder.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from roadrisk.data.errors import DataError, SchemaError
from roadrisk.data.schema import require_valid_header
from roadrisk.data.validate import read_header
from roadrisk.features.spec import (
    APPROVED_NAMES,
    APPROVED_SOURCES,
    AUDIT_COLUMNS,
    CONDITIONAL,
    EXCLUDED,
    SPEC_VERSION,
)
from roadrisk.features.split import SPLIT_YEARS, assert_temporal_policy
from roadrisk.features.transform import exclusion_reasons, transform_row

FEATURE_CSV = "collision-features-v1.csv"
FEATURE_META = "collision-features-v1.meta.json"
OUTPUT_COLUMNS: tuple[str, ...] = AUDIT_COLUMNS + APPROVED_NAMES


def assert_output_dir_is_safe(output_dir: Path, source_file: Path) -> None:
    """Refuse to write features into the raw directory or onto the source file."""

    resolved = output_dir.resolve()
    source = source_file.resolve()
    raw_dir = source.parent
    if resolved == source or resolved == raw_dir or _is_relative_to(resolved, raw_dir):
        raise DataError(f"Refusing to write features into the raw data path: {resolved}")


def build_feature_table(
    source_path: Path,
    output_dir: Path,
    *,
    source_meta: Mapping[str, object],
    generated_at: str,
) -> dict[str, object]:
    """Write the feature CSV and a small provenance file. Return the provenance."""

    assert_temporal_policy()
    assert_output_dir_is_safe(output_dir, source_path)
    header = require_valid_header(read_header(source_path))
    missing_sources = tuple(name for name in APPROVED_SOURCES if name not in header.columns)
    if missing_sources:
        raise SchemaError("Approved source columns are missing: " + ", ".join(missing_sources))
    _reject_forbidden_outputs(OUTPUT_COLUMNS)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / FEATURE_CSV
    meta_path = output_dir / FEATURE_META
    read_rows = 0
    kept = 0
    exclusions: Counter[str] = Counter()
    by_split: Counter[str] = Counter()
    positive_by_split: Counter[str] = Counter()

    with source_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        with csv_path.open("w", newline="", encoding="utf-8") as out_handle:
            writer = csv.DictWriter(
                out_handle,
                fieldnames=OUTPUT_COLUMNS,
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in reader:
                read_rows += 1
                reasons = exclusion_reasons(row)
                if reasons:
                    exclusions.update(reasons)
                    continue
                record = transform_row(row)
                if record is None:
                    exclusions.update(["transform_rejected"])
                    continue
                writer.writerow(record)
                kept += 1
                by_split[record["split"]] += 1
                if record["severity_serious_or_fatal"] == "1":
                    positive_by_split[record["split"]] += 1

    provenance = {
        "feature_spec_version": SPEC_VERSION,
        "generated_at": generated_at,
        "source": dict(source_meta),
        "model_input_columns": list(APPROVED_NAMES),
        "audit_columns": list(AUDIT_COLUMNS),
        "conditional_columns": [field.source_column for field in CONDITIONAL],
        "excluded_columns": [field.source_column for field in EXCLUDED],
        "target": {
            "source_column": "collision_severity",
            "output_column": "severity_serious_or_fatal",
            "positive_codes": ["1", "2"],
            "negative_codes": ["3"],
            "question": (
                "Given a reported personal-injury collision, was it fatal or serious "
                "rather than slight?"
            ),
        },
        "split_policy": {name: list(years) for name, years in SPLIT_YEARS.items()},
        "imputation": "none",
        "learned_encoding": "not fitted",
        "rows": {
            "read": read_rows,
            "retained": kept,
            "excluded": read_rows - kept,
            "exclusion_reason_counts": dict(sorted(exclusions.items())),
            "by_split": {name: by_split[name] for name in SPLIT_YEARS},
            "positive_rows_by_split": {name: positive_by_split[name] for name in SPLIT_YEARS},
        },
    }
    meta_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return provenance


def _reject_forbidden_outputs(columns: Sequence[str]) -> None:
    """The model-input slice of the output must be the approved allowlist."""

    from roadrisk.features.spec import require_model_inputs

    model_inputs = [name for name in columns if name not in AUDIT_COLUMNS]
    require_model_inputs(model_inputs)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
