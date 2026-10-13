"""Deterministic collision-table audit.

The audit reads a verified CSV and returns aggregate counts. It does not
rewrite the source file, impute values, or fit a model.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from roadrisk.data.codebook import ALLOWED_CODES, MISSING_CODE, SEVERITY_LABELS
from roadrisk.data.errors import DataError
from roadrisk.data.schema import (
    EXCLUDED_FROM_FEATURES,
    ID_COLUMN,
    LABEL_COLUMN,
    POSITIVE_SEVERITY_CODES,
    require_valid_header,
)

TRAIN_YEARS = ("2021", "2022", "2023")
VALIDATION_YEARS = ("2024",)
TEST_YEARS = ("2025",)
ACCEPTED_YEARS = frozenset(TRAIN_YEARS + VALIDATION_YEARS + TEST_YEARS)
VALID_SEVERITY = frozenset({"1", "2", "3"})
FREQUENCY_CAP = 50
# Plausibility window for Great Britain. A point outside it is suspicious,
# not an automatic deletion.
GB_LATITUDE = (49.5, 61.1)
GB_LONGITUDE = (-8.8, 2.2)

# Every column on the audited extract has one role. New columns stay out of
# the predictor list until someone classifies them.
COLUMN_ROLES: dict[str, str] = {
    "collision_index": "identifier",
    "collision_ref_no": "identifier",
    "collision_year": "split_key",
    "police_force": "administrative",
    "local_authority_district": "administrative",
    "local_authority_ons_district": "administrative",
    "local_authority_highway": "administrative",
    "lsoa_of_accident_location": "administrative",
    "collision_severity": "target",
    "number_of_vehicles": "post_outcome",
    "number_of_casualties": "post_outcome",
    "did_police_officer_attend_scene_of_accident": "post_outcome",
    "enhanced_severity_collision": "target_derived",
    "collision_injury_based": "target_derived",
    "collision_adjusted_severity_serious": "target_derived",
    "collision_adjusted_severity_slight": "target_derived",
    "local_authority_highway_current": "domain_decision",
    "first_road_number": "domain_decision",
    "second_road_number": "domain_decision",
    "junction_detail_historic": "domain_decision",
    "pedestrian_crossing_human_control_historic": "domain_decision",
    "pedestrian_crossing_physical_facilities_historic": "domain_decision",
    "carriageway_hazards_historic": "domain_decision",
    "carriageway_hazards": "domain_decision",
    "longitude": "potential_predictor",
    "latitude": "potential_predictor",
    "location_easting_osgr": "potential_predictor",
    "location_northing_osgr": "potential_predictor",
    "date": "potential_predictor",
    "day_of_week": "potential_predictor",
    "time": "potential_predictor",
    "first_road_class": "potential_predictor",
    "second_road_class": "potential_predictor",
    "road_type": "potential_predictor",
    "speed_limit": "potential_predictor",
    "junction_detail": "potential_predictor",
    "junction_control": "potential_predictor",
    "pedestrian_crossing": "potential_predictor",
    "light_conditions": "potential_predictor",
    "weather_conditions": "potential_predictor",
    "road_surface_conditions": "potential_predictor",
    "special_conditions_at_site": "potential_predictor",
    "urban_or_rural_area": "potential_predictor",
    "trunk_road_flag": "potential_predictor",
}

ADJUSTED_SERIOUS = "collision_adjusted_severity_serious"
ADJUSTED_SLIGHT = "collision_adjusted_severity_slight"


def audit_csv(path: Path, *, source: Mapping[str, object], generated_at: str) -> dict[str, object]:
    """Audit one collision CSV. The file is opened read-only."""

    header = _read_header(path)
    require_valid_header(header)
    return _audit_header_and_rows(path, header, source=source, generated_at=generated_at)


def population_reasons(year: str, severity: str, index: str = "present") -> tuple[str, ...]:
    """Return exclusion reasons for the planned supervised population.

    A row is retained when it has an identifier, the year is in the named
    split, and the severity code is 1, 2, or 3. Reasons are labels for the
    report. The source file is not rewritten.
    """

    reasons: list[str] = []
    if not index.strip():
        reasons.append("blank_collision_index")
    if severity not in VALID_SEVERITY:
        reasons.append("invalid_or_missing_severity")
    if year not in ACCEPTED_YEARS:
        reasons.append("year_outside_planned_split")
    return tuple(reasons)


def _audit_header_and_rows(
    path: Path,
    header: list[str],
    *,
    source: Mapping[str, object],
    generated_at: str,
) -> dict[str, object]:
    columns = [column.strip() for column in header]
    trackers = {name: _ColumnTracker() for name in columns}
    year_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    severity_by_year: Counter[tuple[str, str]] = Counter()
    exclusion_reasons: Counter[str] = Counter()
    excluded_rows = 0
    first_digest: dict[str, str] = {}
    duplicate_ids = 0
    blank_ids = 0
    conflicting_duplicates = 0
    date_blank = 0
    date_invalid = 0
    year_date_mismatch = 0
    time_blank = 0
    time_invalid = 0
    coordinate = _CoordinateTally()
    grid = _GridTally(
        "location_easting_osgr" in columns and "location_northing_osgr" in columns
    )
    adjusted = _AdjustedTally()
    weight_by_severity: Counter[tuple[str, str]] = Counter()
    enhanced_by_severity: Counter[tuple[str, str]] = Counter()
    injury_by_severity: Counter[tuple[str, str]] = Counter()
    rows = 0

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            rows += 1
            row = {key: (value or "") for key, value in raw.items()}
            for name in columns:
                trackers[name].add(row.get(name, ""))
            index = row.get(ID_COLUMN, "").strip()
            digest = _row_digest(columns, row)
            if not index:
                blank_ids += 1
            elif index in first_digest:
                duplicate_ids += 1
                if first_digest[index] != digest:
                    conflicting_duplicates += 1
            else:
                first_digest[index] = digest
            year = row.get("collision_year", "").strip()
            severity = row.get(LABEL_COLUMN, "").strip()
            year_counts[year or "(blank)"] += 1
            severity_counts[severity or "(blank)"] += 1
            severity_by_year[(year or "(blank)", severity or "(blank)")] += 1
            reasons = population_reasons(year, severity, index)
            if reasons:
                excluded_rows += 1
                exclusion_reasons.update(reasons)
            date_text = row.get("date", "").strip()
            parsed_year = _parse_date(date_text)
            if not date_text:
                date_blank += 1
            elif parsed_year is None:
                date_invalid += 1
            elif year.isdigit() and int(year) != parsed_year:
                year_date_mismatch += 1
            time_text = row.get("time", "").strip()
            if not time_text:
                time_blank += 1
            elif _parse_time(time_text) is None:
                time_invalid += 1
            coordinate.add(row.get("longitude", ""), row.get("latitude", ""))
            grid.add(row.get("location_easting_osgr", ""), row.get("location_northing_osgr", ""))
            weight_kind = adjusted.add(row.get(ADJUSTED_SERIOUS, ""), row.get(ADJUSTED_SLIGHT, ""))
            weight_by_severity[(severity or "(blank)", weight_kind)] += 1
            enhanced_by_severity[
                (
                    severity or "(blank)",
                    row.get("enhanced_severity_collision", "").strip() or "(blank)",
                )
            ] += 1
            injury_by_severity[
                (
                    severity or "(blank)",
                    row.get("collision_injury_based", "").strip() or "(blank)",
                )
            ] += 1

    retained = rows - excluded_rows
    target = _target_summary(severity_counts, rows)
    splits = _split_summary(year_counts, severity_by_year)
    columns_out = [_column_summary(name, trackers[name], rows) for name in columns]
    inventory = _inventory(columns)
    findings = _findings(
        rows=rows,
        target=target,
        excluded_rows=excluded_rows,
        duplicate_ids=duplicate_ids,
        conflicting_duplicates=conflicting_duplicates,
        blank_ids=blank_ids,
        date_invalid=date_invalid,
        year_date_mismatch=year_date_mismatch,
        time_invalid=time_invalid,
        coordinate=coordinate,
        grid=grid,
        columns_out=columns_out,
        enhanced_by_severity=enhanced_by_severity,
    )
    return {
        "generated_at": generated_at,
        "source": dict(source),
        "row_count": rows,
        "column_count": len(columns),
        "population": {
            "rules": [
                "Retain a row when collision_index is present.",
                "Retain a row when collision_severity is 1, 2, or 3.",
                "Retain a row when collision_year is 2021, 2022, 2023, 2024, or 2025.",
                "Do not drop rows for missing coordinates, coded-missing predictors, or weights.",
            ],
            "retained_rows": retained,
            "excluded_rows": excluded_rows,
            "retained_percent": _percent(retained, rows),
            "excluded_percent": _percent(excluded_rows, rows),
            "exclusion_reason_counts": dict(sorted(exclusion_reasons.items())),
        },
        "target": target,
        "splits": splits,
        "duplicates": {
            "duplicate_collision_index_rows": duplicate_ids,
            "blank_collision_index_rows": blank_ids,
            "conflicting_duplicate_rows": conflicting_duplicates,
        },
        "time": {
            "blank_dates": date_blank,
            "invalid_dates": date_invalid,
            "year_date_mismatches": year_date_mismatch,
            "blank_times": time_blank,
            "invalid_times": time_invalid,
            "date_format": "DD/MM/YYYY",
            "time_format": "HH:MM",
        },
        "coordinates": coordinate.to_dict(),
        "national_grid": grid.to_dict(),
        "adjusted_fields": adjusted.to_dict(weight_by_severity),
        "related_severity_fields": {
            "enhanced_severity_collision": {
                "status": "not_interchangeable",
                "reason": (
                    "The codebook calls this enhanced_collision_severity. Codes are 1 Fatal, "
                    "5 Very Serious, 6 Moderately Serious, 7 Less Serious, 3 Slight, and -1 "
                    "for data missing or out of range. A value of -1 is not a severity class, "
                    "and this audit does not replace collision_severity with it."
                ),
                "by_recorded_severity": _pair_rows(enhanced_by_severity),
            },
            "collision_injury_based": {
                "status": "reporting_system_flag",
                "reason": (
                    "0 means severity reporting and 1 means injury-code reporting in the codebook. "
                    "The flag describes how severity was recorded. It is not a severity class."
                ),
                "by_recorded_severity": _pair_rows(injury_by_severity),
            },
        },
        "columns": columns_out,
        "feature_inventory": inventory,
        "findings": findings,
        "checks_not_run": _checks_not_run(columns_out, grid_present=grid.present),
        "leakage_columns_confirmed_present": [
            name for name in EXCLUDED_FROM_FEATURES if name in columns
        ],
    }


class _ColumnTracker:
    def __init__(self) -> None:
        self.missing = 0
        self.values: Counter[str] = Counter()
        self.capped = False

    def add(self, raw: str) -> None:
        text = raw.strip()
        if text == "":
            self.missing += 1
            return
        if self.capped:
            return
        self.values[text] += 1
        if len(self.values) > FREQUENCY_CAP:
            self.capped = True
            self.values.clear()


class _CoordinateTally:
    def __init__(self) -> None:
        self.missing_either = 0
        self.non_numeric = 0
        self.outside_gb = 0
        self.origin = 0
        self.observed = 0
        self.lon_min: float | None = None
        self.lon_max: float | None = None
        self.lat_min: float | None = None
        self.lat_max: float | None = None

    def add(self, longitude: str, latitude: str) -> None:
        lon_text = longitude.strip()
        lat_text = latitude.strip()
        if not lon_text or not lat_text:
            self.missing_either += 1
            return
        try:
            lon = float(lon_text)
            lat = float(lat_text)
        except ValueError:
            self.non_numeric += 1
            return
        self.observed += 1
        self.lon_min = lon if self.lon_min is None else min(self.lon_min, lon)
        self.lon_max = lon if self.lon_max is None else max(self.lon_max, lon)
        self.lat_min = lat if self.lat_min is None else min(self.lat_min, lat)
        self.lat_max = lat if self.lat_max is None else max(self.lat_max, lat)
        if lon == 0 and lat == 0:
            self.origin += 1
        elif not (
            GB_LONGITUDE[0] <= lon <= GB_LONGITUDE[1] and GB_LATITUDE[0] <= lat <= GB_LATITUDE[1]
        ):
            self.outside_gb += 1

    def to_dict(self) -> dict[str, object]:
        return {
            "missing_latitude_or_longitude": self.missing_either,
            "non_numeric": self.non_numeric,
            "outside_great_britain_window": self.outside_gb,
            "origin_points": self.origin,
            "numeric_points": self.observed,
            "longitude_min": self.lon_min,
            "longitude_max": self.lon_max,
            "latitude_min": self.lat_min,
            "latitude_max": self.lat_max,
            "window": {
                "latitude": list(GB_LATITUDE),
                "longitude": list(GB_LONGITUDE),
            },
        }


class _GridTally:
    """British National Grid window. Outside values are suspicious, not deleted."""

    EASTING = (0.0, 700_000.0)
    NORTHING = (0.0, 1_300_000.0)

    def __init__(self, present: bool) -> None:
        self.present = present
        self.missing_either = 0
        self.non_numeric = 0
        self.outside = 0
        self.both_zero = 0
        self.observed = 0

    def add(self, easting: str, northing: str) -> None:
        if not self.present:
            return
        east_text = easting.strip()
        north_text = northing.strip()
        if not east_text or not north_text:
            self.missing_either += 1
            return
        try:
            east = float(east_text)
            north = float(north_text)
        except ValueError:
            self.non_numeric += 1
            return
        self.observed += 1
        if east == 0 and north == 0:
            self.both_zero += 1
        elif not (
            self.EASTING[0] <= east <= self.EASTING[1]
            and self.NORTHING[0] <= north <= self.NORTHING[1]
        ):
            self.outside += 1

    def to_dict(self) -> dict[str, object]:
        if not self.present:
            return {
                "status": "not_run",
                "reason": "location_easting_osgr or location_northing_osgr is absent.",
            }
        return {
            "status": "ran",
            "missing_easting_or_northing": self.missing_either,
            "non_numeric": self.non_numeric,
            "both_zero": self.both_zero,
            "outside_great_britain_grid": self.outside,
            "numeric_points": self.observed,
            "window": {"easting": list(self.EASTING), "northing": list(self.NORTHING)},
        }


class _AdjustedTally:
    def __init__(self) -> None:
        self.blank = 0
        self.non_numeric = 0
        self.both_zero = 0
        self.unit_interval_pair = 0
        self.other = 0
        self.serious_min: float | None = None
        self.serious_max: float | None = None
        self.slight_min: float | None = None
        self.slight_max: float | None = None

    def add(self, serious: str, slight: str) -> str:
        serious_text = serious.strip()
        slight_text = slight.strip()
        if not serious_text or not slight_text:
            self.blank += 1
            return "blank"
        try:
            serious_value = float(serious_text)
            slight_value = float(slight_text)
        except ValueError:
            self.non_numeric += 1
            return "non_numeric"
        self.serious_min = (
            serious_value if self.serious_min is None else min(self.serious_min, serious_value)
        )
        self.serious_max = (
            serious_value if self.serious_max is None else max(self.serious_max, serious_value)
        )
        self.slight_min = (
            slight_value if self.slight_min is None else min(self.slight_min, slight_value)
        )
        self.slight_max = (
            slight_value if self.slight_max is None else max(self.slight_max, slight_value)
        )
        if serious_value == 0 and slight_value == 0:
            self.both_zero += 1
            return "both_zero"
        if abs(serious_value + slight_value - 1) <= 1e-6:
            self.unit_interval_pair += 1
            if serious_value in {0.0, 1.0} and slight_value in {0.0, 1.0}:
                return "one_hot"
            return "fractional_pair"
        self.other += 1
        return "other"

    def to_dict(self, by_severity: Counter[tuple[str, str]]) -> dict[str, object]:
        return {
            "status": "not_a_class_label",
            "reason": (
                "These columns are numeric weights from the DfT severity adjustment. "
                "They are not codes for fatal, serious, or slight, and this audit does not "
                "convert them into a replacement target."
            ),
            "blank_rows": self.blank,
            "non_numeric_rows": self.non_numeric,
            "both_zero_rows": self.both_zero,
            "weights_sum_to_one_rows": self.unit_interval_pair,
            "other_rows": self.other,
            "serious_min": self.serious_min,
            "serious_max": self.serious_max,
            "slight_min": self.slight_min,
            "slight_max": self.slight_max,
            "pattern_by_recorded_severity": [
                {"collision_severity": severity, "pattern": pattern, "rows": count}
                for (severity, pattern), count in sorted(by_severity.items())
            ],
        }


def _column_summary(name: str, tracker: _ColumnTracker, rows: int) -> dict[str, object]:
    allowed = ALLOWED_CODES.get(name)
    observed = set(tracker.values)
    unexpected = (
        tuple(sorted(observed - allowed)) if allowed is not None and not tracker.capped else ()
    )
    absent = tuple(sorted(allowed - observed)) if allowed is not None and not tracker.capped else ()
    coded_missing = (
        tracker.values.get(MISSING_CODE, 0) if allowed and MISSING_CODE in allowed else 0
    )
    distinct = None if tracker.capped else len(tracker.values)
    top = () if tracker.capped else tuple(tracker.values.most_common(15))
    non_missing = rows - tracker.missing
    dominant_share = None
    if not tracker.capped and tracker.values and non_missing:
        dominant_share = _percent(tracker.values.most_common(1)[0][1], non_missing)
    return {
        "name": name,
        "role": COLUMN_ROLES.get(name, "domain_decision"),
        "missing_rows": tracker.missing,
        "missing_percent": _percent(tracker.missing, rows),
        "distinct_values": distinct,
        "frequency_capped": tracker.capped,
        "coded_missing_rows": coded_missing,
        "unexpected_codes": list(unexpected),
        "defined_codes_not_observed": list(absent),
        "code_check": "ran" if allowed is not None and not tracker.capped else "not_run",
        "dominant_non_missing_percent": dominant_share,
        "most_common": [{"value": value, "rows": count} for value, count in top],
    }


def _inventory(columns: Sequence[str]) -> list[dict[str, str]]:
    return [{"column": name, "role": COLUMN_ROLES.get(name, "domain_decision")} for name in columns]


def _target_summary(counts: Counter[str], rows: int) -> dict[str, object]:
    invalid = {code: count for code, count in sorted(counts.items()) if code not in VALID_SEVERITY}
    positive = sum(counts.get(code, 0) for code in POSITIVE_SEVERITY_CODES)
    negative = counts.get("3", 0)
    classes = [
        {
            "code": code,
            "label": SEVERITY_LABELS[code],
            "class": "positive" if code in POSITIVE_SEVERITY_CODES else "negative",
            "rows": counts.get(code, 0),
            "percent": _percent(counts.get(code, 0), rows),
        }
        for code in ("1", "2", "3")
    ]
    enhanced_note = (
        "enhanced_severity_collision is a finer scale collected with injury-based reporting. "
        "Its codebook value -1 means data missing or out of range. It is not a substitute label."
    )
    return {
        "column": LABEL_COLUMN,
        "question": (
            "Given a reported personal-injury collision, was it fatal or serious "
            "rather than slight?"
        ),
        "positive_codes": ["1", "2"],
        "negative_codes": ["3"],
        "classes": classes,
        "positive_rows": positive,
        "positive_percent": _percent(positive, rows),
        "negative_rows": negative,
        "negative_percent": _percent(negative, rows),
        "invalid_or_missing": invalid,
        "status": "supported_with_unresolved_alternatives",
        "status_reason": (
            "Every modelling rule uses collision_severity codes 1, 2, and 3. "
            "The enhanced scale and the adjustment weights remain separate fields. " + enhanced_note
        ),
    }


def _split_summary(
    year_counts: Counter[str],
    severity_by_year: Counter[tuple[str, str]],
) -> dict[str, object]:
    def block(name: str, years: Sequence[str]) -> dict[str, object]:
        count = sum(year_counts.get(year, 0) for year in years)
        positive = sum(
            severity_by_year.get((year, code), 0)
            for year in years
            for code in POSITIVE_SEVERITY_CODES
        )
        return {
            "name": name,
            "years": list(years),
            "rows": count,
            "positive_rows": positive,
            "positive_percent": _percent(positive, count),
        }

    other = {
        year: count for year, count in sorted(year_counts.items()) if year not in ACCEPTED_YEARS
    }
    return {
        "training": block("training", TRAIN_YEARS),
        "validation": block("validation", VALIDATION_YEARS),
        "test": block("test", TEST_YEARS),
        "rows_outside_planned_years": other,
        "by_year": [
            {
                "year": year,
                "rows": year_counts[year],
                "severity": {
                    code: severity_by_year.get((year, code), 0) for code in ("1", "2", "3")
                },
            }
            for year in sorted(year_counts)
        ],
    }


def _findings(
    *,
    rows: int,
    target: Mapping[str, object],
    excluded_rows: int,
    duplicate_ids: int,
    conflicting_duplicates: int,
    blank_ids: int,
    date_invalid: int,
    year_date_mismatch: int,
    time_invalid: int,
    coordinate: _CoordinateTally,
    grid: _GridTally,
    columns_out: Sequence[Mapping[str, object]],
    enhanced_by_severity: Counter[tuple[str, str]],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    invalid = target["invalid_or_missing"]
    assert isinstance(invalid, dict)
    if invalid:
        findings.append(
            {
                "id": "invalid_severity",
                "level": "warning",
                "summary": "Some rows do not have collision_severity 1, 2, or 3.",
            }
        )
    else:
        findings.append(
            {
                "id": "severity_codes_match_codebook",
                "level": "info",
                "summary": "Every row uses collision_severity 1, 2, or 3.",
            }
        )
    if excluded_rows == 0:
        findings.append(
            {
                "id": "population_keeps_every_row",
                "level": "info",
                "summary": f"The planned population rules retain all {rows} rows.",
            }
        )
    else:
        findings.append(
            {
                "id": "population_excludes_rows",
                "level": "warning",
                "summary": f"The planned population rules exclude {excluded_rows} rows.",
            }
        )
    if duplicate_ids or blank_ids or conflicting_duplicates:
        findings.append(
            {
                "id": "identifier_problems",
                "level": "warning",
                "summary": "collision_index is blank, repeated, or repeated with different rows.",
            }
        )
    else:
        findings.append(
            {
                "id": "identifiers_unique",
                "level": "info",
                "summary": "collision_index is present and unique.",
            }
        )
    if date_invalid or time_invalid or year_date_mismatch:
        findings.append(
            {
                "id": "temporal_inconsistency",
                "level": "warning",
                "summary": "At least one date, time, or year/date pair failed the format check.",
            }
        )
    else:
        findings.append(
            {
                "id": "temporal_fields_consistent",
                "level": "info",
                "summary": "Dates, times, and collision_year agree on the checked rows.",
            }
        )
    if coordinate.non_numeric or coordinate.outside_gb or coordinate.origin:
        findings.append(
            {
                "id": "coordinate_anomalies",
                "level": "warning",
                "summary": "Some coordinates are non-numeric, at 0,0, or outside the GB window.",
            }
        )
    if coordinate.missing_either:
        findings.append(
            {
                "id": "coordinates_incomplete",
                "level": "warning",
                "summary": (
                    f"{coordinate.missing_either} rows are missing latitude or longitude. "
                    "They stay in the severity population."
                ),
            }
        )
    if grid.present and (grid.non_numeric or grid.outside or grid.both_zero):
        findings.append(
            {
                "id": "national_grid_anomalies",
                "level": "warning",
                "summary": (
                    "Some easting or northing values are non-numeric, both zero, "
                    "or outside the Great Britain grid window. They are not deleted."
                ),
            }
        )
    enhanced_missing = sum(
        count
        for (_severity, value), count in enhanced_by_severity.items()
        if value in {"-1", "(blank)"}
    )
    enhanced_total = sum(enhanced_by_severity.values())
    if enhanced_total and enhanced_missing == enhanced_total:
        findings.append(
            {
                "id": "enhanced_severity_unavailable",
                "level": "info",
                "summary": (
                    "enhanced_severity_collision is missing or coded -1 on every row, "
                    "so it cannot replace collision_severity."
                ),
            }
        )
    elif enhanced_missing:
        findings.append(
            {
                "id": "enhanced_severity_partial",
                "level": "info",
                "summary": (
                    "enhanced_severity_collision is missing or coded -1 on part of the extract. "
                    "It stays a separate field."
                ),
            }
        )
    for column in columns_out:
        unexpected = column["unexpected_codes"]
        if isinstance(unexpected, list) and unexpected:
            findings.append(
                {
                    "id": f"unexpected_codes_{column['name']}",
                    "level": "warning",
                    "summary": f"{column['name']} contains codes absent from the transcribed list.",
                }
            )
    findings.append(
        {
            "id": "adjusted_fields_not_a_label",
            "level": "info",
            "summary": (
                "Adjustment weights were measured and were not mapped to fatal, serious, or slight."
            ),
        }
    )
    for column in columns_out:
        distinct = column["distinct_values"]
        dominant = column["dominant_non_missing_percent"]
        if column.get("frequency_capped") or column["role"] == "identifier":
            continue
        if isinstance(distinct, int) and distinct <= 1:
            findings.append(
                {
                    "id": f"constant_{column['name']}",
                    "level": "info",
                    "summary": f"{column['name']} has {distinct} distinct non-missing value.",
                }
            )
            continue
        if not isinstance(dominant, float) or dominant < 99:
            continue
        top = column.get("most_common")
        top_value = ""
        if isinstance(top, list) and top and isinstance(top[0], dict):
            top_value = str(top[0].get("value", ""))
        if top_value == MISSING_CODE:
            findings.append(
                {
                    "id": f"mostly_coded_missing_{column['name']}",
                    "level": "warning",
                    "summary": (
                        f"{column['name']} is coded {MISSING_CODE} on {dominant}% "
                        "of non-missing rows."
                    ),
                }
            )
        else:
            findings.append(
                {
                    "id": f"near_constant_{column['name']}",
                    "level": "info",
                    "summary": (
                        f"{column['name']} has one value on {dominant}% of non-missing rows."
                    ),
                }
            )
    return findings


_DEDICATED_CHECKS = frozenset(
    {
        "location_easting_osgr",
        "location_northing_osgr",
        "longitude",
        "latitude",
        "date",
        "time",
    }
)
_CODE_LIST_ROLES = frozenset({"potential_predictor", "domain_decision", "administrative"})


def _checks_not_run(
    columns_out: Sequence[Mapping[str, object]],
    *,
    grid_present: bool,
) -> list[dict[str, str]]:
    skipped = []
    for column in columns_out:
        name = str(column["name"])
        if name in _DEDICATED_CHECKS:
            continue
        role = COLUMN_ROLES.get(name, "domain_decision")
        if name in ALLOWED_CODES:
            if column.get("frequency_capped"):
                skipped.append(
                    {
                        "check": "code_list",
                        "column": name,
                        "reason": "Too many distinct values to compare with the code list.",
                    }
                )
            continue
        if role not in _CODE_LIST_ROLES:
            continue
        if column.get("frequency_capped"):
            reason = "Distinct values exceeded the cap, and no code list is transcribed."
        else:
            reason = "No code list for this column is transcribed in codebook.py."
        skipped.append({"check": "code_list", "column": name, "reason": reason})
    if not grid_present:
        skipped.append(
            {
                "check": "national_grid",
                "column": "location_easting_osgr",
                "reason": "Easting or northing is absent, so the grid check did not run.",
            }
        )
    skipped.append(
        {
            "check": "model_score",
            "column": "",
            "reason": "This phase does not train a model or score the test year.",
        }
    )
    return skipped


def _pair_rows(counts: Counter[tuple[str, str]]) -> list[dict[str, object]]:
    return [
        {"collision_severity": severity, "value": value, "rows": count}
        for (severity, value), count in sorted(counts.items())
    ]


def _parse_date(value: str) -> int | None:
    try:
        return datetime.strptime(value, "%d/%m/%Y").year
    except ValueError:
        return None


def _parse_time(value: str) -> bool | None:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        return None
    return True


def _row_digest(columns: Sequence[str], row: Mapping[str, str]) -> str:
    payload = "\x1f".join(row.get(column, "") for column in columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _percent(count: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(100 * count / total, 4)


def assert_output_dir_is_safe(output_dir: Path, source_file: Path) -> None:
    """Refuse to write a report beside or on top of the raw extract."""

    resolved = output_dir.resolve()
    if resolved == source_file.resolve() or resolved == source_file.parent.resolve():
        raise DataError(f"Refusing to write an audit report into the raw data path: {resolved}")
    if _is_relative_to(resolved, source_file.parent.resolve()):
        raise DataError(
            f"Refusing to write an audit report inside the raw data directory: {resolved}"
        )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _read_header(path: Path) -> list[str]:
    from roadrisk.data.validate import read_header

    return read_header(path)
