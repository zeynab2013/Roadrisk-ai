"""Audit tests. Every CSV here is synthetic."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from roadrisk.data.__main__ import main
from roadrisk.data.errors import DataError, SchemaError
from roadrisk.data.integrity import sha256_file
from roadrisk.data.quality import (
    ADJUSTED_SERIOUS,
    ADJUSTED_SLIGHT,
    audit_csv,
    population_reasons,
)
from roadrisk.data.schema import REQUIRED_COLUMNS

HEADER = [
    *REQUIRED_COLUMNS,
    "enhanced_severity_collision",
    "collision_injury_based",
    ADJUSTED_SERIOUS,
    ADJUSTED_SLIGHT,
    "number_of_casualties",
]


def _row(**overrides: str) -> dict[str, str]:
    base = dict.fromkeys(HEADER, "1")
    base.update(
        {
            "collision_index": "SYNTHETIC-1",
            "collision_year": "2021",
            "collision_severity": "3",
            "date": "15/03/2021",
            "time": "08:30",
            "longitude": "-1.5",
            "latitude": "53.4",
            "enhanced_severity_collision": "-1",
            "collision_injury_based": "0",
            ADJUSTED_SERIOUS: "0",
            ADJUSTED_SLIGHT: "1",
            "number_of_casualties": "1",
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
        "catalogue_url": "https://example.test/catalog",
    }


def test_valid_binary_target_mapping(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(
        path,
        [
            _row(
                collision_index="SYNTHETIC-1",
                collision_severity="1",
                **{
                    ADJUSTED_SERIOUS: "0",
                    ADJUSTED_SLIGHT: "0",
                },
            ),
            _row(
                collision_index="SYNTHETIC-2",
                collision_severity="2",
                collision_year="2024",
                date="01/01/2024",
            ),
            _row(
                collision_index="SYNTHETIC-3",
                collision_severity="3",
                collision_year="2025",
                date="01/01/2025",
            ),
        ],
    )
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    target = report["target"]
    assert isinstance(target, dict)
    assert target["positive_rows"] == 2
    assert target["negative_rows"] == 1
    assert target["invalid_or_missing"] == {}
    assert target["status"] == "supported_with_unresolved_alternatives"
    population = report["population"]
    assert isinstance(population, dict)
    assert population["retained_rows"] == 3
    assert population["excluded_rows"] == 0
    splits = report["splits"]
    assert isinstance(splits, dict)
    training = splits["training"]
    assert isinstance(training, dict)
    assert training["rows"] == 1


def test_missing_and_unexpected_severity_are_excluded(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(
        path,
        [
            _row(collision_index="SYNTHETIC-1", collision_severity="9"),
            _row(collision_index="SYNTHETIC-2", collision_severity=""),
        ],
    )
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    population = report["population"]
    assert isinstance(population, dict)
    assert population["excluded_rows"] == 2
    reasons = population["exclusion_reason_counts"]
    assert reasons == {"invalid_or_missing_severity": 2}
    target = report["target"]
    assert isinstance(target, dict)
    assert target["invalid_or_missing"] == {"(blank)": 1, "9": 1}


def test_duplicate_identifiers_and_conflicts(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(
        path,
        [
            _row(collision_index="SYNTHETIC-1", collision_severity="1"),
            _row(collision_index="SYNTHETIC-1", collision_severity="3"),
        ],
    )
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    duplicates = report["duplicates"]
    assert isinstance(duplicates, dict)
    assert duplicates["duplicate_collision_index_rows"] == 1
    assert duplicates["conflicting_duplicate_rows"] == 1


def test_invalid_year_is_excluded_and_date_mismatch_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(
        path,
        [
            _row(collision_index="SYNTHETIC-1", collision_year="1999", date="01/01/1999"),
            _row(collision_index="SYNTHETIC-2", collision_year="", date="01/01/2021"),
            _row(collision_index="SYNTHETIC-3", collision_year="2021", date="01/01/2022"),
        ],
    )
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    population = report["population"]
    assert isinstance(population, dict)
    assert population["excluded_rows"] == 2
    assert population["retained_rows"] == 1
    time = report["time"]
    assert isinstance(time, dict)
    assert time["year_date_mismatches"] == 1
    assert population_reasons("1999", "3") == ("year_outside_planned_split",)
    assert population_reasons("2021", "3") == ()


def test_missing_column_raises(tmp_path: Path) -> None:
    header = [column for column in HEADER if column != "weather_conditions"]
    path = tmp_path / "synthetic.csv"
    _write_csv(path, [_row()], header)
    with pytest.raises(SchemaError, match="weather_conditions"):
        audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")


def test_malformed_date_and_coordinate(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(
        path,
        [
            _row(collision_index="SYNTHETIC-1", date="32/13/2021", latitude="north"),
            _row(collision_index="SYNTHETIC-2", longitude="", latitude=""),
            _row(collision_index="SYNTHETIC-3", longitude="40", latitude="10"),
        ],
    )
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    time = report["time"]
    coordinates = report["coordinates"]
    assert isinstance(time, dict)
    assert isinstance(coordinates, dict)
    assert time["invalid_dates"] == 1
    assert coordinates["non_numeric"] == 1
    assert coordinates["missing_latitude_or_longitude"] == 1
    assert coordinates["outside_great_britain_window"] == 1


def test_identical_inputs_produce_identical_audits(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(path, [_row()])
    first = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    second = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    assert first == second


def test_adjusted_fields_are_not_treated_as_a_label(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(
        path,
        [
            _row(
                collision_index="SYNTHETIC-1",
                collision_severity="1",
                **{ADJUSTED_SERIOUS: "0", ADJUSTED_SLIGHT: "0"},
            )
        ],
    )
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    adjusted = report["adjusted_fields"]
    assert isinstance(adjusted, dict)
    assert adjusted["status"] == "not_a_class_label"
    patterns = adjusted["pattern_by_recorded_severity"]
    assert {"collision_severity": "1", "pattern": "both_zero", "rows": 1} in patterns
    inventory = report["feature_inventory"]
    assert isinstance(inventory, list)
    roles = {item["column"]: item["role"] for item in inventory if isinstance(item, dict)}
    assert roles[ADJUSTED_SERIOUS] == "target_derived"
    assert roles["number_of_casualties"] == "post_outcome"
    assert roles["collision_severity"] == "target"


def test_audit_command_stops_when_checksum_does_not_match(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "raw" / "synthetic.csv"
    _write_csv(data_file, [_row()])
    before = data_file.read_bytes()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
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
                        "sha256": "0" * 64,
                        "bytes": data_file.stat().st_size,
                        "required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    code = main(
        [
            "audit",
            "--manifest",
            str(manifest_path),
            "--root",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert code == 1
    assert data_file.read_bytes() == before
    assert not output_dir.exists()


def test_audit_command_writes_reports_for_a_verified_synthetic_file(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "raw" / "synthetic.csv"
    _write_csv(data_file, [_row()])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
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
                        "sha256": sha256_file(data_file),
                        "bytes": data_file.stat().st_size,
                        "required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    code = main(
        [
            "audit",
            "--manifest",
            str(manifest_path),
            "--root",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert code == 0
    payload = json.loads((output_dir / "collision-audit.json").read_text(encoding="utf-8"))
    assert payload["row_count"] == 1
    assert (
        "fatal or serious"
        in (output_dir / "collision-audit.md").read_text(encoding="utf-8").lower()
    )


def test_unexpected_weather_code_is_named(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(path, [_row(collision_index="SYNTHETIC-1", weather_conditions="99")])
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    columns = report["columns"]
    assert isinstance(columns, list)
    weather = next(
        item
        for item in columns
        if isinstance(item, dict) and item["name"] == "weather_conditions"
    )
    assert weather["unexpected_codes"] == ["99"]


def test_mostly_coded_missing_column_is_reported(tmp_path: Path) -> None:
    header = [*HEADER, "local_authority_district"]
    rows = [
        _row(collision_index=f"SYNTHETIC-{index}", local_authority_district="-1")
        for index in range(100)
    ]
    rows.append(_row(collision_index="SYNTHETIC-other", local_authority_district="241"))
    path = tmp_path / "synthetic.csv"
    _write_csv(path, rows, header)
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    findings = report["findings"]
    assert isinstance(findings, list)
    match = next(
        item
        for item in findings
        if isinstance(item, dict) and item["id"] == "mostly_coded_missing_local_authority_district"
    )
    assert match["level"] == "warning"


def test_blank_identifier_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    _write_csv(path, [_row(collision_index="")])
    report = audit_csv(path, source=_source(), generated_at="2026-10-09T00:00:00+00:00")
    population = report["population"]
    assert isinstance(population, dict)
    assert population["excluded_rows"] == 1
    assert population["exclusion_reason_counts"] == {"blank_collision_index": 1}
    assert population_reasons("2021", "3", "") == ("blank_collision_index",)


def test_report_directory_cannot_replace_the_raw_file(tmp_path: Path) -> None:
    from roadrisk.data.quality import assert_output_dir_is_safe

    source = tmp_path / "raw" / "synthetic.csv"
    source.parent.mkdir()
    source.write_text("x", encoding="utf-8")
    with pytest.raises(DataError, match="raw"):
        assert_output_dir_is_safe(source.parent, source)
