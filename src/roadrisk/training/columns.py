"""Model columns taken from the approved feature specification."""

from __future__ import annotations

from roadrisk.data.errors import FeatureContractError
from roadrisk.features.spec import APPROVED, APPROVED_NAMES, LABEL_OUTPUT

NUMERIC_FEATURES: tuple[str, ...] = tuple(
    field.name for field in APPROVED if field.data_type == "numeric"
)
CATEGORICAL_FEATURES: tuple[str, ...] = tuple(
    field.name for field in APPROVED if field.data_type == "categorical"
)
LABEL_COLUMN = LABEL_OUTPUT
POSITIVE_LABEL = 1
NEGATIVE_LABEL = 0

_KNOWN_TYPES = {"numeric", "categorical"}
_unexpected = sorted({field.data_type for field in APPROVED} - _KNOWN_TYPES)
if _unexpected:
    names = ", ".join(_unexpected)
    raise FeatureContractError(f"Approved features have an unknown data type: {names}")
if set(NUMERIC_FEATURES) | set(CATEGORICAL_FEATURES) != set(APPROVED_NAMES):
    raise FeatureContractError("Numeric and categorical features do not cover the allowlist")
