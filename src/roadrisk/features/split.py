"""Temporal split for the collision-severity task.

Assignment uses ``collision_year`` only. It does not read the target.
The ranges do not overlap, and 2025 is the test year alone.
"""

from __future__ import annotations

from roadrisk.data.errors import FeatureContractError
from roadrisk.data.quality import TEST_YEARS, TRAIN_YEARS, VALIDATION_YEARS

SPLIT_YEARS: dict[str, tuple[str, ...]] = {
    "training": TRAIN_YEARS,
    "validation": VALIDATION_YEARS,
    "test": TEST_YEARS,
}


def assign_split(year: str) -> str | None:
    """Return training, validation, or test. Unknown years return None."""

    text = year.strip()
    for name, years in SPLIT_YEARS.items():
        if text in years:
            return name
    return None


def overlapping_years() -> tuple[tuple[str, str, str], ...]:
    """Return ``(split_a, split_b, year)`` when one year sits in two splits."""

    names = tuple(SPLIT_YEARS)
    found: list[tuple[str, str, str]] = []
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            shared = set(SPLIT_YEARS[left]) & set(SPLIT_YEARS[right])
            found.extend((left, right, year) for year in sorted(shared))
    return tuple(found)


def assert_temporal_policy() -> None:
    """Raise when the named ranges overlap or 2025 is not test-only."""

    overlaps = overlapping_years()
    if overlaps:
        left, right, year = overlaps[0]
        raise FeatureContractError(f"{year} is in both the {left} and {right} splits")
    if assign_split("2025") != "test":
        raise FeatureContractError("2025 must be assigned to the test split")
    for year in ("2021", "2022", "2023", "2024"):
        if assign_split(year) == "test":
            raise FeatureContractError(f"{year} must not be in the test split")
    if set(TEST_YEARS) != {"2025"}:
        raise FeatureContractError("2025 must be the only test year")
