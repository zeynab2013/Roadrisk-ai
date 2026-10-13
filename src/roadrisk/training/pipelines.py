"""Untuned baseline pipelines.

Each pipeline fits its imputer and encoder on the rows it is given.
Callers must pass 2021–2023 only. Numeric scaling is used for logistic
regression and is not applied to one-hot columns.
"""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from roadrisk.training.columns import CATEGORICAL_FEATURES, NUMERIC_FEATURES

SEED = 42
MISSING_CATEGORY = "missing"

# Fixed baseline capacity. These values were chosen before validation scores
# were inspected. They are not a search result.
BASELINE_SETTINGS: dict[str, dict[str, object]] = {
    "dummy": {
        "strategy": "prior",
        "random_state": SEED,
        "preprocessing": "median numeric imputation, constant categorical fill, one-hot",
    },
    "logistic_regression": {
        "solver": "lbfgs",
        "max_iter": 500,
        "class_weight": "balanced",
        "random_state": SEED,
        "preprocessing": "median numeric impute, scale numeric columns only, one-hot categories",
    },
    "random_forest": {
        "n_estimators": 100,
        "max_depth": 12,
        "min_samples_leaf": 25,
        "class_weight": "balanced_subsample",
        "random_state": SEED,
        "n_jobs": -1,
        "preprocessing": "median numeric impute, constant category fill, one-hot, no scaling",
    },
    "hist_gradient_boosting": {
        "max_iter": 100,
        "learning_rate": 0.1,
        "max_leaf_nodes": 31,
        "early_stopping": False,
        "class_weight": "balanced",
        "random_state": SEED,
        "preprocessing": (
            "median numeric imputation, ordinal categories with unknown values left missing, "
            "native categorical support, no scaling"
        ),
    },
}


def make_baseline(name: str) -> Pipeline:
    """Return one unfitted baseline pipeline."""

    if name == "dummy":
        model = DummyClassifier(strategy="prior", random_state=SEED)
        preprocess = _one_hot_preprocess(scale_numeric=False)
    elif name == "logistic_regression":
        model = LogisticRegression(
            solver="lbfgs",
            max_iter=500,
            class_weight="balanced",
            random_state=SEED,
        )
        preprocess = _one_hot_preprocess(scale_numeric=True)
    elif name == "random_forest":
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=12,
            min_samples_leaf=25,
            class_weight="balanced_subsample",
            random_state=SEED,
            n_jobs=-1,
        )
        preprocess = _one_hot_preprocess(scale_numeric=False)
    elif name == "hist_gradient_boosting":
        model = HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.1,
            max_leaf_nodes=31,
            early_stopping=False,
            class_weight="balanced",
            random_state=SEED,
            categorical_features=_categorical_mask(),
        )
        preprocess = _ordinal_preprocess()
    else:
        raise ValueError(f"Unknown baseline: {name}")
    return Pipeline([("preprocess", preprocess), ("model", model)])


def baseline_names() -> tuple[str, ...]:
    """Names in comparison order. Dummy stays first."""

    return (
        "dummy",
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
    )


def _one_hot_preprocess(*, scale_numeric: bool) -> ColumnTransformer:
    numeric_steps: list[tuple[str, object]] = [
        ("imputer", SimpleImputer(strategy="median")),
    ]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="constant", fill_value=MISSING_CATEGORY)),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", Pipeline(numeric_steps), list(NUMERIC_FEATURES)),
            ("categorical", categorical, list(CATEGORICAL_FEATURES)),
        ]
    )


def _ordinal_preprocess() -> ColumnTransformer:
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="constant", fill_value=MISSING_CATEGORY)),
            (
                "encoder",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=float("nan"),
                    encoded_missing_value=float("nan"),
                ),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", SimpleImputer(strategy="median"), list(NUMERIC_FEATURES)),
            ("categorical", categorical, list(CATEGORICAL_FEATURES)),
        ]
    )


def _categorical_mask() -> list[bool]:
    """Mask for the ordinal pipeline output: numeric columns, then categories."""

    return [False] * len(NUMERIC_FEATURES) + [True] * len(CATEGORICAL_FEATURES)
