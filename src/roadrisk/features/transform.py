"""Deterministic row transforms.

No statistic is computed from a collection of rows. Unknown tokens come
from the codebook, not from frequencies in the extract.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from roadrisk.data.codebook import ALLOWED_CODES, MISSING_CODE
from roadrisk.data.quality import population_reasons
from roadrisk.data.schema import ID_COLUMN, LABEL_COLUMN, POSITIVE_SEVERITY_CODES
from roadrisk.features.spec import (
    APPROVED,
    MISSING_TOKEN,
    UNEXPECTED_TOKEN,
    UNKNOWN_CODES,
    UNKNOWN_TOKEN,
    FeatureField,
)
from roadrisk.features.split import assign_split

_WEEKDAYS = frozenset({"1", "2", "3", "4", "5", "6", "7"})
_SEASONS = {
    12: "winter",
    1: "winter",
    2: "winter",
    3: "spring",
    4: "spring",
    5: "spring",
    6: "summer",
    7: "summer",
    8: "summer",
    9: "autumn",
    10: "autumn",
    11: "autumn",
}


def map_target(severity: str) -> str | None:
    """Map a severity code to 1 (fatal or serious) or 0 (slight)."""

    code = severity.strip()
    if code in POSITIVE_SEVERITY_CODES:
        return "1"
    if code == "3":
        return "0"
    return None


def normalize_category(field: FeatureField, raw: str) -> str:
    """Map one categorical source value to a stable token."""

    text = raw.strip()
    allowed = ALLOWED_CODES.get(field.source_column, frozenset())
    unknown = UNKNOWN_CODES.get(field.source_column, frozenset())
    if text == "" or text == MISSING_CODE:
        return MISSING_TOKEN
    if text in unknown:
        return UNKNOWN_TOKEN
    if text not in allowed:
        return UNEXPECTED_TOKEN
    return text


def transform_clock(time_text: str) -> str:
    """Return the hour as a decimal string, or blank when time is invalid."""

    try:
        parsed = datetime.strptime(time_text.strip(), "%H:%M")
    except ValueError:
        return ""
    return str(parsed.hour)


def transform_date_parts(date_text: str) -> tuple[str, str]:
    """Return ``(month, season)``. Both are blank when the date is invalid."""

    try:
        parsed = datetime.strptime(date_text.strip(), "%d/%m/%Y")
    except ValueError:
        return "", ""
    return str(parsed.month), _SEASONS[parsed.month]


def weekday_from_date(date_text: str) -> str:
    """Return the STATS19 weekday code for a valid date, else blank.

    The codebook uses 1 for Sunday through 7 for Saturday.
    """

    try:
        parsed = datetime.strptime(date_text.strip(), "%d/%m/%Y")
    except ValueError:
        return ""
    return str((parsed.weekday() + 1) % 7 + 1)


def transform_weekday(day_of_week: str, date_text: str) -> str:
    """Prefer a valid ``day_of_week`` code, otherwise derive it from the date."""

    code = day_of_week.strip()
    if code in _WEEKDAYS:
        return code
    derived = weekday_from_date(date_text)
    if derived:
        return derived
    if code == "" or code == MISSING_CODE:
        return MISSING_TOKEN
    return UNEXPECTED_TOKEN


def transform_coordinate(raw: str) -> str:
    """Keep a numeric coordinate string. Blank means missing. No imputation."""

    text = raw.strip()
    if not text:
        return ""
    try:
        float(text)
    except ValueError:
        return ""
    return text


def exclusion_reasons(row: Mapping[str, str]) -> tuple[str, ...]:
    """Population rules shared with the quality audit. The target is not a split key."""

    return population_reasons(
        row.get("collision_year", ""),
        row.get(LABEL_COLUMN, ""),
        row.get(ID_COLUMN, ""),
    )


def transform_features(row: Mapping[str, str]) -> dict[str, str]:
    """Return approved model inputs for one row. Does not include the label."""

    date_text = row.get("date", "")
    month, season = transform_date_parts(date_text)
    values = {
        "longitude": transform_coordinate(row.get("longitude", "")),
        "latitude": transform_coordinate(row.get("latitude", "")),
        "hour": transform_clock(row.get("time", "")),
        "weekday": transform_weekday(row.get("day_of_week", ""), date_text),
        "month": month,
        "season": season,
    }
    for field in APPROVED:
        if field.name in values:
            continue
        values[field.name] = normalize_category(field, row.get(field.source_column, ""))
    return {field.name: values[field.name] for field in APPROVED}


def transform_row(row: Mapping[str, str]) -> dict[str, str] | None:
    """Return one output record, or None when the population rules reject the row."""

    if exclusion_reasons(row):
        return None
    year = row.get("collision_year", "").strip()
    split = assign_split(year)
    if split is None:
        return None
    severity = row.get(LABEL_COLUMN, "").strip()
    label = map_target(severity)
    if label is None:
        return None
    record = {
        "collision_index": row.get(ID_COLUMN, "").strip(),
        "collision_year": year,
        "split": split,
        LABEL_COLUMN: severity,
        "severity_serious_or_fatal": label,
    }
    record.update(transform_features(row))
    return record
