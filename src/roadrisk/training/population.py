"""Split the feature table without letting 2025 into fitting or selection."""

from __future__ import annotations

from roadrisk.data.errors import FeatureContractError
from roadrisk.features.spec import APPROVED_NAMES, require_model_inputs
from roadrisk.features.split import assert_temporal_policy
from roadrisk.training.columns import LABEL_COLUMN

REQUIRED_CONTEXT = ("collision_year", "split", LABEL_COLUMN)


def assert_excludes_test(frame, *, purpose: str) -> None:
    """Raise when a frame used for fitting or selection contains the test year."""

    years = set(frame["collision_year"].astype(str))
    splits = set(frame["split"].astype(str))
    if "2025" in years or "test" in splits:
        raise FeatureContractError(
            f"{purpose} received 2025 or the test split. "
            "That year is reserved and is not used for training or model selection."
        )


def assert_validation_frame(frame, *, purpose: str) -> None:
    """Raise unless every row is the 2024 validation split and nothing else."""

    if len(frame) == 0:
        raise FeatureContractError(f"{purpose} received an empty validation frame.")
    missing = [name for name in ("collision_year", "split") if name not in frame.columns]
    if missing:
        raise FeatureContractError(f"{purpose} is missing columns: " + ", ".join(missing))
    years = set(frame["collision_year"].astype(str))
    splits = set(frame["split"].astype(str))
    if years != {"2024"} or splits != {"validation"}:
        raise FeatureContractError(
            f"{purpose} must use only the 2024 validation split. "
            f"Received years {sorted(years)} and splits {sorted(splits)}."
        )


def training_and_validation(frame):
    """Return training rows, validation rows, and the unused 2025 row count.

    The returned frames do not include 2025. Their labels are not compared
    with the test year.
    """

    assert_temporal_policy()
    missing = [name for name in (*REQUIRED_CONTEXT, *APPROVED_NAMES) if name not in frame.columns]
    if missing:
        raise FeatureContractError("Feature table is missing columns: " + ", ".join(missing))
    require_model_inputs(list(APPROVED_NAMES))
    years = frame["collision_year"].astype(str)
    splits = frame["split"].astype(str)
    mislabeled_year = (years == "2025") & (splits != "test")
    mislabeled_split = (splits == "test") & (years != "2025")
    if mislabeled_year.any() or mislabeled_split.any():
        raise FeatureContractError(
            "collision_year and split disagree. 2025 must be the test split and nothing else."
        )
    test_rows = int((splits == "test").sum())
    train = frame.loc[splits == "training"].copy()
    validation = frame.loc[splits == "validation"].copy()
    other = int((~splits.isin(["training", "validation", "test"])).sum())
    if other:
        raise FeatureContractError(f"{other} rows are outside training, validation, and test")
    assert_excludes_test(train, purpose="training")
    assert_excludes_test(validation, purpose="validation")
    return train, validation, test_rows


def held_out_rows(frame):
    """Return the 2025 test rows.

    Selection must not call this. The final evaluation calls it once, after
    the model, calibration, and threshold are frozen.
    """

    assert_temporal_policy()
    missing = [name for name in (*REQUIRED_CONTEXT, *APPROVED_NAMES) if name not in frame.columns]
    if missing:
        raise FeatureContractError("Feature table is missing columns: " + ", ".join(missing))
    years = frame["collision_year"].astype(str)
    splits = frame["split"].astype(str)
    mislabeled_year = (years == "2025") & (splits != "test")
    mislabeled_split = (splits == "test") & (years != "2025")
    if mislabeled_year.any() or mislabeled_split.any():
        raise FeatureContractError(
            "collision_year and split disagree. 2025 must be the test split and nothing else."
        )
    test = frame.loc[splits == "test"].copy()
    if test.empty:
        raise FeatureContractError("The test split is empty")
    if set(test["collision_year"].astype(str)) != {"2025"}:
        raise FeatureContractError("The test split contains a year other than 2025")
    return test
