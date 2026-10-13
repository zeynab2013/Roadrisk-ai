"""Summaries of model output by the approved urban or rural class.

`urban_or_rural_area` is an approved feature with codes 1 Urban, 2 Rural,
and 3 Unallocated. Administrative district fields are not approved and are
not in the feature table. `local_authority_district` is deprecated on nearly
every audited row, so it is not a grouping field.

A higher share of HIGH model output is a share of recorded collisions. It
is not evidence that an area is more dangerous, and it is not an
accident-probability map. There is no traffic-exposure denominator.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.inference.risk import CATEGORIES, assign_category

GROUP_FIELD = "urban_or_rural_area"
GROUP_LABELS = {"1": "Urban", "2": "Rural", "3": "Unallocated"}
GROUP_REASON = (
    "urban_or_rural_area is an approved feature with a closed code list. "
    "ONS district and highway authority codes are conditional and are not "
    "emitted. The older local_authority_district code is deprecated on "
    "nearly all audited rows."
)


def summarize_groups(
    frame: pd.DataFrame,
    probabilities,
    bands: Mapping[str, object],
    *,
    minimum_support: int,
    population: str,
) -> dict[str, object]:
    """Aggregate aligned probabilities. Labels are not read."""

    if minimum_support < 1:
        raise DataError("The area support minimum must be at least 1")
    if GROUP_FIELD not in frame.columns:
        raise FeatureContractError(f"Area summary is missing {GROUP_FIELD}")
    scores = np.asarray(probabilities, dtype=float)
    if len(frame) != scores.size:
        raise DataError("Area summary probabilities do not match the row count")
    if scores.size and (not np.isfinite(scores).all() or np.any((scores < 0.0) | (scores > 1.0))):
        raise DataError("Area summary probabilities must be finite and in [0, 1]")
    categories = [assign_category(float(value), bands) for value in scores] if scores.size else []
    missing = 0
    unsupported = 0
    buckets: dict[str, list[float]] = {code: [] for code in GROUP_LABELS}
    bucket_categories: dict[str, list[str]] = {code: [] for code in GROUP_LABELS}
    for code, probability, category in zip(
        frame[GROUP_FIELD].tolist(),
        scores.tolist(),
        categories,
        strict=True,
    ):
        token = _token(code)
        if token is None:
            missing += 1
            continue
        if token not in GROUP_LABELS:
            unsupported += 1
            continue
        buckets[token].append(float(probability))
        bucket_categories[token].append(category)
    groups = []
    for code in GROUP_LABELS:
        values = buckets[code]
        assigned = bucket_categories[code]
        counts = {name: assigned.count(name) for name in CATEGORIES}
        total = len(values)
        groups.append(
            {
                "area_id": code,
                "label": GROUP_LABELS[code],
                "collisions": total,
                "category_counts": counts,
                "category_shares": {
                    name: (counts[name] / total if total else None) for name in CATEGORIES
                },
                "mean_predicted_probability": float(np.mean(values)) if total else None,
            }
        )
    supported = [row for row in groups if row["collisions"] >= minimum_support]
    supported.sort(
        key=lambda row: (-float(row["category_shares"]["HIGH"] or 0.0), str(row["area_id"]))
    )
    return {
        "grouping_field": GROUP_FIELD,
        "grouping_reason": GROUP_REASON,
        "population": population,
        "minimum_support": minimum_support,
        "rows": int(len(frame)),
        "missing_location_rows": missing,
        "unsupported_location_rows": unsupported,
        "groups": groups,
        "supported_groups": supported,
        "not_estimated": "Whether a collision occurs, or whether an area is unsafe.",
        "limitation": (
            "Counts are recorded personal-injury collisions in the stated "
            "population. They are not traffic exposure, population, or a "
            "rate of collisions. A group below the support minimum is omitted "
            "from supported_groups. Presence on that list is a share of model "
            "output among recorded collisions, not a safety ranking."
        ),
    }


def _token(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "missing"}:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text
