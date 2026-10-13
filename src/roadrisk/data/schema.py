"""Collision-table contract for the selected DfT extract.

Column names come from the header of
``dft-road-casualty-statistics-collision-last-5-years.csv`` retrieved on
9 October 2026. Code labels for ``collision_severity`` come from the
``2024_code_list`` sheet in the 2025 open-dataset data guide:

- 1 Fatal
- 2 Serious
- 3 Slight

The positive class is fatal or serious (codes 1 and 2). That is the
severity of a reported collision, not the probability that a collision
occurs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from roadrisk.data.errors import FeatureLeakageError, SchemaError

LABEL_COLUMN = "collision_severity"
ID_COLUMN = "collision_index"
POSITIVE_SEVERITY_CODES = frozenset({"1", "2"})

REQUIRED_COLUMNS: tuple[str, ...] = (
    "collision_index",
    "collision_year",
    "collision_ref_no",
    "longitude",
    "latitude",
    "local_authority_ons_district",
    "collision_severity",
    "date",
    "day_of_week",
    "time",
    "road_type",
    "speed_limit",
    "junction_detail",
    "junction_control",
    "pedestrian_crossing",
    "light_conditions",
    "weather_conditions",
    "road_surface_conditions",
    "urban_or_rural_area",
)

# Present on the published collision extract. They describe the crash after
# it occurred, an adjustment weight, or the reporting system. They are not
# default predictors.
EXCLUDED_FROM_FEATURES: tuple[str, ...] = (
    "number_of_vehicles",
    "number_of_casualties",
    "did_police_officer_attend_scene_of_accident",
    "enhanced_severity_collision",
    "collision_injury_based",
    "collision_adjusted_severity_serious",
    "collision_adjusted_severity_slight",
)


@dataclass(frozen=True)
class HeaderReport:
    """Result of comparing a header with the collision contract."""

    columns: tuple[str, ...]
    missing_required: tuple[str, ...]
    duplicate_names: tuple[str, ...]
    excluded_present: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_required and not self.duplicate_names


def inspect_header(columns: Sequence[str]) -> HeaderReport:
    """Classify a header without raising."""

    cleaned = tuple(column.strip() for column in columns)
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in cleaned:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    missing = tuple(name for name in REQUIRED_COLUMNS if name not in seen)
    excluded = tuple(name for name in EXCLUDED_FROM_FEATURES if name in seen)
    return HeaderReport(
        columns=cleaned,
        missing_required=missing,
        duplicate_names=tuple(duplicates),
        excluded_present=excluded,
    )


def require_valid_header(columns: Sequence[str]) -> HeaderReport:
    """Return the header report or raise ``SchemaError``."""

    report = inspect_header(columns)
    if report.duplicate_names:
        names = ", ".join(report.duplicate_names)
        raise SchemaError(f"Header repeats column names: {names}")
    if report.missing_required:
        names = ", ".join(report.missing_required)
        raise SchemaError(f"Missing required columns: {names}")
    return report


def require_features_exclude_leakage(feature_names: Sequence[str]) -> None:
    """Reject a feature list that includes the label or a post-event column."""

    blocked = set(EXCLUDED_FROM_FEATURES) | {LABEL_COLUMN}
    found = tuple(name for name in feature_names if name in blocked)
    if found:
        names = ", ".join(found)
        raise FeatureLeakageError(
            f"These columns are excluded from the default feature set: {names}"
        )
