"""Score a fitted probability model on the approved feature columns."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.features.spec import APPROVED_NAMES


def feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Return model inputs in the approved column order."""

    missing = [name for name in APPROVED_NAMES if name not in frame.columns]
    if missing:
        raise FeatureContractError("Feature table is missing columns: " + ", ".join(missing))
    return frame.loc[:, list(APPROVED_NAMES)]


def positive_scores(estimator, frame: pd.DataFrame) -> np.ndarray:
    """Probability of the positive class, column order unchanged."""

    _require_probability_model(estimator)
    probabilities = estimator.predict_proba(feature_matrix(frame))
    classes = [int(value) for value in estimator.classes_]
    if 1 not in classes:
        raise FeatureContractError("The fitted model has no positive class to score")
    return np.asarray(probabilities[:, classes.index(1)], dtype=float)


def load_estimator(path: Path):
    """Load a joblib classifier. Missing or incompatible files raise."""

    if not path.is_file():
        raise DataError(f"Model artifact is missing: {path}")
    try:
        estimator = joblib.load(path)
    except Exception as exc:
        raise DataError(f"Model artifact could not be read: {path}") from exc
    _require_probability_model(estimator)
    return estimator


def _require_probability_model(estimator) -> None:
    if not hasattr(estimator, "predict_proba") or not hasattr(estimator, "classes_"):
        raise DataError("Model artifact is not a probability classifier")
