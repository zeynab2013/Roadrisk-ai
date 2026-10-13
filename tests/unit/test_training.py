"""Baseline training tests. Frames are synthetic and do not use the extract."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sklearn")

import joblib
import pandas as pd

from roadrisk.data.errors import FeatureContractError, FeatureLeakageError
from roadrisk.features.spec import APPROVED_NAMES, require_model_inputs
from roadrisk.features.transform import map_target
from roadrisk.training.columns import CATEGORICAL_FEATURES, LABEL_COLUMN, NUMERIC_FEATURES
from roadrisk.training.metrics import choose_provisional, positive_class_metrics
from roadrisk.training.pipelines import make_baseline
from roadrisk.training.population import training_and_validation
from roadrisk.training.run import fit_baselines, normalize_model_frame


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    records = []
    for index, overrides in enumerate(rows):
        row: dict[str, object] = {name: "1" for name in APPROVED_NAMES}
        row.update(
            {
                "collision_index": f"SYNTHETIC-{index}",
                "collision_year": "2021",
                "split": "training",
                LABEL_COLUMN: 0,
                "longitude": "0.0",
                "latitude": "51.5",
                "hour": "8",
                "month": "1",
                "weekday": "1",
                "season": "winter",
                "weather_conditions": "1",
            }
        )
        row.update(overrides)
        records.append(row)
    return pd.DataFrame.from_records(records)


def test_target_mapping_matches_the_feature_contract() -> None:
    assert map_target("1") == "1"
    assert map_target("2") == "1"
    assert map_target("3") == "0"
    assert map_target("9") is None
    frame = _frame([{LABEL_COLUMN: 1}, {LABEL_COLUMN: 0}])
    assert set(frame[LABEL_COLUMN]) == {0, 1}


def test_allowlist_is_the_only_model_input() -> None:
    require_model_inputs(list(APPROVED_NAMES))
    with pytest.raises(FeatureLeakageError):
        require_model_inputs(["collision_index"])
    with pytest.raises(FeatureLeakageError):
        require_model_inputs(["enhanced_severity_collision"])
    assert "collision_index" not in NUMERIC_FEATURES
    assert "collision_index" not in CATEGORICAL_FEATURES


def test_temporal_split_keeps_2025_out_of_selection() -> None:
    frame = _frame(
        [
            {"collision_year": "2021", "split": "training", LABEL_COLUMN: 0},
            {"collision_year": "2023", "split": "training", LABEL_COLUMN: 1},
            {"collision_year": "2024", "split": "validation", LABEL_COLUMN: 1},
            {"collision_year": "2025", "split": "test", LABEL_COLUMN: 0},
        ]
    )
    train, validation, test_rows = training_and_validation(frame)
    assert test_rows == 1
    assert set(train["collision_year"]) == {"2021", "2023"}
    assert set(validation["collision_year"]) == {"2024"}
    assert "2025" not in set(train["split"])
    bad = frame.copy()
    bad.loc[3, "split"] = "training"
    with pytest.raises(FeatureContractError, match="2025"):
        training_and_validation(bad)


def test_imputer_uses_training_rows_only() -> None:
    frame = _frame(
        [
            {"longitude": "0", LABEL_COLUMN: 0},
            {"longitude": "10", LABEL_COLUMN: 1},
            {"collision_year": "2024", "split": "validation", "longitude": "100", LABEL_COLUMN: 0},
        ]
    )
    train, validation, _test_rows = training_and_validation(frame)
    pipeline = make_baseline("logistic_regression")
    prepared = normalize_model_frame(train)
    pipeline.fit(prepared.loc[:, list(APPROVED_NAMES)], prepared[LABEL_COLUMN].to_numpy())
    numeric = pipeline.named_steps["preprocess"].named_transformers_["numeric"]
    imputer = numeric.named_steps["imputer"]
    longitude_index = list(NUMERIC_FEATURES).index("longitude")
    assert imputer.statistics_[longitude_index] == pytest.approx(5.0)
    scored = pipeline.predict_proba(normalize_model_frame(validation).loc[:, list(APPROVED_NAMES)])
    assert scored.shape == (1, 2)


def test_unseen_validation_category_is_ignored() -> None:
    frame = _frame(
        [
            {"weather_conditions": "1", LABEL_COLUMN: 0},
            {"weather_conditions": "2", LABEL_COLUMN: 1},
            {
                "collision_year": "2024",
                "split": "validation",
                "weather_conditions": "NEW",
                LABEL_COLUMN: 1,
            },
        ]
    )
    train, validation, _test_rows = training_and_validation(frame)
    fitted = fit_baselines(train, validation)
    logistic = next(row for row in fitted if row["model"] == "logistic_regression")
    encoder = (
        logistic["pipeline"]
        .named_steps["preprocess"]
        .named_transformers_["categorical"]
        .named_steps["encoder"]
    )
    weather_index = list(CATEGORICAL_FEATURES).index("weather_conditions")
    assert "NEW" not in set(encoder.categories_[weather_index])
    boosting = next(row for row in fitted if row["model"] == "hist_gradient_boosting")
    assert boosting["metrics"]["rows"] == 1


def test_missing_numeric_and_categorical_values_score() -> None:
    frame = _frame(
        [
            {"longitude": "", "season": "", LABEL_COLUMN: 0},
            {"longitude": "1.0", "season": "summer", LABEL_COLUMN: 1},
            {
                "collision_year": "2024",
                "split": "validation",
                "longitude": "",
                "season": "",
                LABEL_COLUMN: 0,
            },
        ]
    )
    train, validation, _test_rows = training_and_validation(frame)
    fitted = fit_baselines(train, validation)
    assert len(fitted) == 4
    for row in fitted:
        assert row["metrics"]["rows"] == 1


def test_positive_class_metrics_and_one_class_edge() -> None:
    metrics = positive_class_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["confusion_matrix"]["matrix"] == [[2, 0], [0, 2]]
    assert metrics["average_precision_status"] == "defined"
    assert metrics["roc_auc_status"] == "defined"
    assert metrics["brier_status"] == "defined"
    undefined = positive_class_metrics([0, 0], [0.2, 0.4])
    assert undefined["roc_auc_status"] == "undefined"
    assert undefined["roc_auc"] is None


def test_logistic_fit_is_repeatable() -> None:
    frame = _frame(
        [
            {LABEL_COLUMN: 0, "longitude": "0"},
            {LABEL_COLUMN: 1, "longitude": "1"},
            {LABEL_COLUMN: 0, "longitude": "0.2"},
            {LABEL_COLUMN: 1, "longitude": "0.8"},
            {"collision_year": "2024", "split": "validation", LABEL_COLUMN: 1, "longitude": "0.7"},
        ]
    )
    train, validation, _test_rows = training_and_validation(frame)
    first = fit_baselines(train, validation)
    second = fit_baselines(train, validation)
    left = next(row for row in first if row["model"] == "logistic_regression")
    right = next(row for row in second if row["model"] == "logistic_regression")
    assert left["metrics"] == right["metrics"]


def test_saved_pipeline_predicts_the_same_values(tmp_path: Path) -> None:
    frame = _frame(
        [
            {LABEL_COLUMN: 0},
            {LABEL_COLUMN: 1},
            {"collision_year": "2024", "split": "validation", LABEL_COLUMN: 1},
        ]
    )
    train, validation, _test_rows = training_and_validation(frame)
    fitted = fit_baselines(train, validation)
    logistic = next(row for row in fitted if row["model"] == "logistic_regression")
    path = tmp_path / "logistic_regression.joblib"
    joblib.dump(logistic["pipeline"], path)
    loaded = joblib.load(path)
    features = normalize_model_frame(validation).loc[:, list(APPROVED_NAMES)]
    original = logistic["pipeline"].predict_proba(features)
    restored = loaded.predict_proba(features)
    assert original.tolist() == restored.tolist()


def test_close_average_precision_prefers_the_lower_brier() -> None:
    results = [
        _result("dummy", average_precision=0.30, brier=0.20),
        _result("logistic_regression", average_precision=0.50, brier=0.18),
        _result("random_forest", average_precision=0.498, brier=0.10),
        _result("hist_gradient_boosting", average_precision=0.40, brier=0.05),
    ]
    decision = choose_provisional(results)
    assert decision["model"] == "random_forest"
    assert decision["models_beating_dummy_average_precision"] == [
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
    ]


def _result(name: str, *, average_precision: float, brier: float) -> dict[str, object]:
    return {
        "model": name,
        "metrics": {"average_precision": average_precision, "brier": brier},
    }
