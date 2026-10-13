"""Feature-contract tests. Every CSV here is synthetic."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from roadrisk.data.errors import DataError, FeatureLeakageError, SchemaError
from roadrisk.data.integrity import sha256_file
from roadrisk.data.schema import EXCLUDED_FROM_FEATURES
from roadrisk.features.__main__ import main
from roadrisk.features.build import build_feature_table
from roadrisk.features.spec import (
    APPROVED,
    APPROVED_NAMES,
    APPROVED_SOURCES,
    LABEL_OUTPUT,
    SPEC_VERSION,
    require_model_inputs,
)
from roadrisk.features.split import assert_temporal_policy, assign_split, overlapping_years
from roadrisk.features.transform import map_target, transform_row

HEADER = [
    "collision_index",
    "collision_year",
    "collision_ref_no",
    "collision_severity",
    "local_authority_ons_district",
    *APPROVED_SOURCES,
    "junction_detail_historic",
    "number_of_casualties",
    "enhanced_severity_collision",
    "collision_adjusted_severity_serious",
]


def _row(**overrides: str) -> dict[str, str]:
    base = dict.fromkeys(HEADER, "1")
    base.update(
        {
            "collision_index": "SYNTHETIC-1",
            "collision_year": "2021",
            "collision_severity": "3",
            "date": "03/01/2021",
            "day_of_week": "1",
            "time": "08:30",
            "longitude": "-1.5",
            "latitude": "53.4",
            "junction_detail": "13",
            "junction_detail_historic": "3",
            "weather_conditions": "1",
            "enhanced_severity_collision": "3",
            "number_of_casualties": "2",
            "collision_adjusted_severity_serious": "0",
        }
    )
    base.update(overrides)
    return base


def _write_csv(path: Path, rows: list[dict[str, str]], header: list[str] | None = None) -> None:
    columns = header or HEADER
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _source() -> dict[str, object]:
    return {
        "dataset_name": "Synthetic catalog",
        "manifest_file_id": "synthetic-collisions",
        "filename": "synthetic.csv",
        "sha256": "synthetic",
        "byte_size": 0,
        "schema_version": 1,
    }


def test_valid_and_invalid_target_codes() -> None:
    assert map_target("1") == "1"
    assert map_target("2") == "1"
    assert map_target("3") == "0"
    assert map_target("9") is None
    assert map_target("") is None
    assert transform_row(_row(collision_severity="1"))["severity_serious_or_fatal"] == "1"
    assert transform_row(_row(collision_severity="9")) is None


def test_approved_feature_order_is_the_model_contract() -> None:
    assert len(APPROVED_NAMES) == 19
    assert APPROVED_NAMES == tuple(field.name for field in APPROVED)
    assert APPROVED_NAMES[0] == "longitude"
    assert APPROVED_NAMES[-1] == "trunk_road_flag"
    assert LABEL_OUTPUT not in APPROVED_NAMES
    assert "collision_severity" not in APPROVED_NAMES
    record = transform_row(_row(longitude="not-a-number", latitude=""))
    assert record is not None
    emitted = [name for name in record if name in APPROVED_NAMES]
    assert emitted == list(APPROVED_NAMES)
    assert record["longitude"] == ""
    assert record["latitude"] == ""
    assert record[LABEL_OUTPUT] == "0"


def test_allowlist_rejects_identifiers_and_target_fields() -> None:
    require_model_inputs(["longitude", "weather_conditions"])
    with pytest.raises(FeatureLeakageError, match="collision_index"):
        require_model_inputs(["collision_index"])
    with pytest.raises(FeatureLeakageError, match="enhanced_severity_collision"):
        require_model_inputs(["enhanced_severity_collision"])
    with pytest.raises(FeatureLeakageError, match="collision_severity"):
        require_model_inputs(["collision_severity"])
    with pytest.raises(FeatureLeakageError, match="carriageway_hazards"):
        require_model_inputs(["carriageway_hazards"])
    for name in EXCLUDED_FROM_FEATURES:
        assert name not in APPROVED_NAMES


def test_forbidden_fields_are_absent_from_the_transformed_row() -> None:
    record = transform_row(_row())
    assert record is not None
    assert "junction_detail_historic" not in record
    assert "number_of_casualties" not in record
    assert "enhanced_severity_collision" not in record
    assert "collision_adjusted_severity_serious" not in record
    assert record["junction_detail"] == "13"
    assert set(record) == set(APPROVED_NAMES) | {
        "collision_index",
        "collision_year",
        "split",
        "collision_severity",
        "severity_serious_or_fatal",
    }


def test_datetime_parts_are_deterministic() -> None:
    first = transform_row(_row())
    second = transform_row(_row())
    assert first == second
    assert first is not None
    assert first["hour"] == "8"
    assert first["month"] == "1"
    assert first["season"] == "winter"
    assert first["weekday"] == "1"
    derived = transform_row(_row(day_of_week=""))
    assert derived is not None
    assert derived["weekday"] == "1"
    kept = transform_row(_row(day_of_week="2"))
    assert kept is not None
    assert kept["weekday"] == "2"


def test_missing_and_unknown_categories() -> None:
    blank = transform_row(_row(weather_conditions=""))
    missing = transform_row(_row(weather_conditions="-1"))
    unknown = transform_row(_row(weather_conditions="9"))
    unexpected = transform_row(_row(weather_conditions="99"))
    fine = transform_row(_row(weather_conditions="1"))
    assert blank is not None and blank["weather_conditions"] == "missing"
    assert missing is not None and missing["weather_conditions"] == "missing"
    assert unknown is not None and unknown["weather_conditions"] == "unknown"
    assert unexpected is not None and unexpected["weather_conditions"] == "unexpected"
    assert fine is not None and fine["weather_conditions"] == "1"
    dark = transform_row(_row(light_conditions="7"))
    assert dark is not None and dark["light_conditions"] == "7"


def test_historic_schema_is_not_a_feature_in_either_year() -> None:
    early = transform_row(_row(collision_year="2021", junction_detail="13"))
    late = transform_row(
        _row(collision_index="SYNTHETIC-2025", collision_year="2025", junction_detail="13")
    )
    assert early is not None and late is not None
    assert early["junction_detail"] == late["junction_detail"] == "13"
    assert early["weather_conditions"] == late["weather_conditions"]
    assert "junction_detail_historic" not in early
    assert early["split"] == "training"
    assert late["split"] == "test"


def test_temporal_policy_keeps_2025_as_test_only() -> None:
    assert_temporal_policy()
    assert overlapping_years() == ()
    assert assign_split("2021") == "training"
    assert assign_split("2023") == "training"
    assert assign_split("2024") == "validation"
    assert assign_split("2025") == "test"
    assert assign_split("2020") is None
    assert assign_split("") is None


def test_invalid_year_and_blank_identifier_are_excluded() -> None:
    assert transform_row(_row(collision_year="1999")) is None
    assert transform_row(_row(collision_year="")) is None
    assert transform_row(_row(collision_index="")) is None


def test_build_is_reproducible_and_reserves_2025(tmp_path: Path) -> None:
    path = tmp_path / "raw" / "synthetic.csv"
    _write_csv(
        path,
        [
            _row(collision_index="SYNTHETIC-2021", collision_year="2021", collision_severity="2"),
            _row(collision_index="SYNTHETIC-2024", collision_year="2024", collision_severity="3"),
            _row(collision_index="SYNTHETIC-2025", collision_year="2025", collision_severity="1"),
            _row(collision_index="SYNTHETIC-bad", collision_year="2019", collision_severity="1"),
        ],
    )
    before = path.read_bytes()
    first_dir = tmp_path / "processed-a"
    second_dir = tmp_path / "processed-b"
    first = build_feature_table(
        path, first_dir, source_meta=_source(), generated_at="2026-10-09T00:00:00+00:00"
    )
    second = build_feature_table(
        path, second_dir, source_meta=_source(), generated_at="2026-10-09T00:00:00+00:00"
    )
    assert first == second
    assert first["feature_spec_version"] == SPEC_VERSION
    rows = first["rows"]
    assert isinstance(rows, dict)
    assert rows["read"] == 4
    assert rows["retained"] == 3
    assert rows["by_split"] == {"training": 1, "validation": 1, "test": 1}
    csv_a = (first_dir / "collision-features-v1.csv").read_bytes()
    csv_b = (second_dir / "collision-features-v1.csv").read_bytes()
    assert csv_a == csv_b
    with (first_dir / "collision-features-v1.csv").open(encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert [row["split"] for row in written] == ["training", "validation", "test"]
    assert written[2]["collision_year"] == "2025"
    assert "number_of_casualties" not in written[0]
    assert path.read_bytes() == before


def test_missing_approved_source_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "raw" / "synthetic.csv"
    header = [name for name in HEADER if name != "first_road_class"]
    _write_csv(path, [_row()], header)
    with pytest.raises(SchemaError, match="first_road_class"):
        build_feature_table(
            path,
            tmp_path / "processed",
            source_meta=_source(),
            generated_at="2026-10-09T00:00:00+00:00",
        )


def test_feature_output_cannot_replace_the_raw_file(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw" / "synthetic.csv"
    _write_csv(raw, [_row()])
    with pytest.raises(DataError, match="raw data"):
        build_feature_table(
            raw,
            raw.parent,
            source_meta=_source(),
            generated_at="2026-10-09T00:00:00+00:00",
        )
    assert raw.is_file()


def test_build_command_stops_on_checksum_mismatch(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "raw" / "synthetic.csv"
    _write_csv(data_file, [_row()])
    before = data_file.read_bytes()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest("0" * 64, data_file.stat().st_size)),
        encoding="utf-8",
    )
    code = main(
        [
            "build",
            "--manifest",
            str(manifest_path),
            "--root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "data" / "processed"),
        ]
    )
    assert code == 1
    assert data_file.read_bytes() == before
    assert not (tmp_path / "data" / "processed" / "collision-features-v1.csv").exists()


def test_build_command_writes_a_verified_synthetic_file(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "raw" / "synthetic.csv"
    _write_csv(data_file, [_row(collision_year="2025", collision_severity="2")])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest(sha256_file(data_file), data_file.stat().st_size)),
        encoding="utf-8",
    )
    output_dir = tmp_path / "data" / "processed"
    code = main(
        [
            "build",
            "--manifest",
            str(manifest_path),
            "--root",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert code == 0
    meta_path = output_dir / "collision-features-v1.meta.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["rows"]["by_split"]["test"] == 1
    assert payload["rows"]["by_split"]["training"] == 0
    assert "enhanced_severity_collision" in payload["excluded_columns"]
    assert "longitude" in payload["model_input_columns"]


def _manifest(digest: str, size: int) -> dict[str, object]:
    return {
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
                "id": "synthetic-collisions",
                "role": "collisions",
                "filename": "synthetic.csv",
                "url": "https://example.test/synthetic.csv",
                "directory": "raw",
                "sha256": digest,
                "bytes": size,
                "required": True,
            }
        ],
    }
