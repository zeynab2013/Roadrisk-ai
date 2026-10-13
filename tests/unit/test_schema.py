"""Collision schema tests. Fixtures are synthetic."""

from pathlib import Path

import pytest

from roadrisk.data.errors import DataFileError, FeatureLeakageError, SchemaError
from roadrisk.data.schema import (
    EXCLUDED_FROM_FEATURES,
    LABEL_COLUMN,
    require_features_exclude_leakage,
    require_valid_header,
)
from roadrisk.data.validate import find_duplicate_ids, inspect_csv, read_header

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"


def test_synthetic_collision_header_is_accepted() -> None:
    report = inspect_csv(FIXTURES / "collision_valid.csv", count_rows=True)
    assert report.header.is_valid
    assert report.data_rows == 2
    assert "number_of_casualties" in report.header.excluded_present


def test_missing_required_column_is_named() -> None:
    header = read_header(FIXTURES / "collision_missing_column.csv")
    with pytest.raises(SchemaError, match="weather_conditions"):
        require_valid_header(header)


def test_duplicate_header_name_is_rejected() -> None:
    header = read_header(FIXTURES / "collision_valid.csv")
    header.append("collision_index")
    with pytest.raises(SchemaError, match="collision_index"):
        require_valid_header(header)


def test_leakage_column_cannot_be_a_feature() -> None:
    leaking = EXCLUDED_FROM_FEATURES[0]
    with pytest.raises(FeatureLeakageError, match=leaking):
        require_features_exclude_leakage(["weather_conditions", leaking])
    with pytest.raises(FeatureLeakageError, match=LABEL_COLUMN):
        require_features_exclude_leakage([LABEL_COLUMN])


def test_safe_feature_list_is_accepted() -> None:
    require_features_exclude_leakage(["weather_conditions", "speed_limit"])


def test_duplicate_collision_index_is_reported() -> None:
    duplicates = find_duplicate_ids(FIXTURES / "collision_duplicate_id.csv")
    assert duplicates == ("SYNTHETIC-1",)


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(DataFileError, match="empty"):
        read_header(path)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DataFileError, match="missing"):
        read_header(tmp_path / "absent.csv")
