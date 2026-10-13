"""Phase 6 calibration, threshold, and one-shot test evaluation.

Frames are synthetic. These tests do not read the collision extract or
refit the Phase 5 baselines.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

import joblib
import pandas as pd

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.features.spec import APPROVED_NAMES, SPEC_VERSION
from roadrisk.features.transform import map_target
from roadrisk.training import __main__ as training_main
from roadrisk.training.calibration import (
    choose_calibration,
    fit_calibrator,
    score_fitted_candidates,
)
from roadrisk.training.columns import LABEL_COLUMN
from roadrisk.training.metrics import choose_provisional, positive_class_metrics
from roadrisk.training.phase6 import (
    DECISION_KEYS,
    decision_hash,
    evaluate_frozen,
    file_sha256,
    refuse_existing_evaluation,
    select_from_frame,
)
from roadrisk.training.pipelines import make_baseline
from roadrisk.training.population import held_out_rows, training_and_validation
from roadrisk.training.run import normalize_model_frame
from roadrisk.training.scoring import load_estimator, positive_scores
from roadrisk.training.threshold import (
    THRESHOLD_GRID,
    choose_threshold,
    choose_threshold_on_validation,
)

PUBLISHED_BASELINES = [
    ("dummy", 0.24838744835376064, 0.18691727663849733),
    ("logistic_regression", 0.3313507848292686, 0.23003272689226145),
    ("random_forest", 0.3474253099290746, 0.2301782018711636),
    ("hist_gradient_boosting", 0.34299235426012553, 0.22017245708969874),
]


def test_severity_codes_stay_fatal_or_serious_versus_slight() -> None:
    assert map_target("1") == "1"
    assert map_target("2") == "1"
    assert map_target("3") == "0"
    assert map_target("9") is None


def test_default_threshold_metrics_and_confusion_counts() -> None:
    metrics = positive_class_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert metrics["threshold"] == 0.5
    assert metrics["threshold_note"].startswith("Estimator default of 0.5")
    assert metrics["confusion_matrix"]["matrix"] == [[2, 0], [0, 2]]
    assert metrics["predicted_positive"] == 2
    assert metrics["positive_rows"] == 2
    assert metrics["rows"] == 4
    assert metrics["log_loss_status"] == "defined"
    low = positive_class_metrics([0, 0, 1, 1], [0.1, 0.4, 0.6, 0.9], threshold=0.3)
    high = positive_class_metrics([0, 0, 1, 1], [0.1, 0.4, 0.6, 0.9], threshold=0.8)
    assert low["average_precision"] == high["average_precision"]
    assert low["roc_auc"] == high["roc_auc"]
    assert low["brier"] == high["brier"]
    assert low["log_loss"] == high["log_loss"]
    assert low["predicted_positive"] > high["predicted_positive"]
    with pytest.raises(ValueError, match="threshold"):
        positive_class_metrics([0, 1], [0.2, 0.8], threshold=0)


def test_published_phase5_scores_still_select_gradient_boosting() -> None:
    results = [
        {"model": name, "metrics": {"average_precision": average_precision, "brier": brier}}
        for name, average_precision, brier in PUBLISHED_BASELINES
    ]
    decision = choose_provisional(results)
    assert decision["model"] == "hist_gradient_boosting"


def test_phase5_report_and_artifact_are_preserved() -> None:
    report = Path("docs/baselines.md").read_text(encoding="utf-8")
    assert "Random forest leads on average precision at 0.3474" in report
    assert "Gradient boosting is 0.3430" in report
    assert "2025 has not been scored." in report
    comparison = Path("data/models/baselines-v1/comparison.json")
    if not comparison.is_file():
        pytest.skip("Phase 5 comparison artifact is not in this checkout")
    before = comparison.read_bytes()
    payload = json.loads(before)
    assert payload["provisional_model"]["model"] == "hist_gradient_boosting"
    assert payload["test_year_scored"] is False
    by_name = {row["model"]: row["metrics"] for row in payload["models"]}
    for name, average_precision, brier in PUBLISHED_BASELINES:
        assert by_name[name]["average_precision"] == average_precision
        assert by_name[name]["brier"] == brier
    assert comparison.read_bytes() == before


def test_calibration_rule_rejects_a_worse_or_incomplete_gain() -> None:
    base = _candidate("none", brier=0.20, log_loss=0.50, average_precision=0.40)
    worse = _candidate("sigmoid", brier=0.21, log_loss=0.55, average_precision=0.41)
    isotonic = _candidate("isotonic", brier=0.19, log_loss=0.60, average_precision=0.41)
    decision = choose_calibration([base, worse, isotonic])
    assert decision["method"] == "none"


def test_calibration_rule_rejects_a_large_average_precision_drop() -> None:
    base = _candidate("none", brier=0.20, log_loss=0.50, average_precision=0.40)
    sigmoid = _candidate("sigmoid", brier=0.10, log_loss=0.40, average_precision=0.38)
    isotonic = _candidate("isotonic", brier=0.11, log_loss=0.41, average_precision=0.38)
    decision = choose_calibration([base, sigmoid, isotonic])
    assert decision["method"] == "none"


def test_calibration_rule_prefers_sigmoid_inside_the_brier_band() -> None:
    base = _candidate("none", brier=0.20, log_loss=0.50, average_precision=0.40)
    sigmoid = _candidate("sigmoid", brier=0.1505, log_loss=0.40, average_precision=0.40)
    isotonic = _candidate("isotonic", brier=0.1500, log_loss=0.39, average_precision=0.40)
    decision = choose_calibration([base, sigmoid, isotonic])
    assert decision["method"] == "sigmoid"


def test_calibration_rule_keeps_the_lower_brier_outside_the_band() -> None:
    base = _candidate("none", brier=0.20, log_loss=0.50, average_precision=0.40)
    sigmoid = _candidate("sigmoid", brier=0.16, log_loss=0.40, average_precision=0.40)
    isotonic = _candidate("isotonic", brier=0.14, log_loss=0.39, average_precision=0.39)
    decision = choose_calibration([base, sigmoid, isotonic])
    assert decision["method"] == "isotonic"


def test_calibrator_fit_uses_training_rows_and_is_repeatable() -> None:
    frame = _population()
    train, validation, test_rows = training_and_validation(frame)
    assert test_rows == 2
    prepared = normalize_model_frame(train)
    first = fit_calibrator(
        make_baseline("logistic_regression"),
        prepared,
        method="sigmoid",
        cv_splits=2,
    )
    second = fit_calibrator(
        make_baseline("logistic_regression"),
        prepared,
        method="sigmoid",
        cv_splits=2,
    )
    probe = normalize_model_frame(validation)
    assert positive_scores(first, probe).tolist() == positive_scores(second, probe).tolist()
    mixed = pd.concat([prepared, normalize_model_frame(validation)], ignore_index=True)
    with pytest.raises(FeatureContractError):
        fit_calibrator(
            make_baseline("logistic_regression"),
            mixed,
            method="sigmoid",
            cv_splits=2,
        )


def test_threshold_keeps_half_unless_f1_improves() -> None:
    perfect = choose_threshold([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert perfect["threshold"] == 0.5
    assert 0.5 in THRESHOLD_GRID
    shifted = choose_threshold(
        [0, 0, 0, 0, 1, 1, 1, 1],
        [0.1, 0.2, 0.3, 0.6, 0.4, 0.7, 0.8, 0.9],
    )
    assert shifted["threshold"] != 0.5
    reference = next(row for row in shifted["grid"] if row["threshold"] == 0.5)
    assert shifted["selected_metrics"]["f1"] >= float(reference["metrics"]["f1"]) + 0.01
    ranking = {row["metrics"]["average_precision"] for row in shifted["grid"]}
    assert len(ranking) == 1


def test_threshold_selection_rejects_the_test_split() -> None:
    frame = _population()
    _train, validation, _test_rows = training_and_validation(frame)
    scores = [0.2] * len(validation)
    choose_threshold_on_validation(validation, scores)
    leaked = pd.concat([validation, held_out_rows(frame)], ignore_index=True)
    with pytest.raises(FeatureContractError, match="2025"):
        choose_threshold_on_validation(leaked, [0.2] * len(leaked))


def test_selection_freezes_before_scoring_2025(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def opened(*_args, **_kwargs):
        raise AssertionError("selection opened the 2025 test split")

    monkeypatch.setattr("roadrisk.training.phase6.held_out_rows", opened)
    frame = _population()
    train, _validation, _test_rows = training_and_validation(frame)
    reference = tmp_path / "hist_gradient_boosting.joblib"
    pipeline = make_baseline("hist_gradient_boosting")
    prepared = normalize_model_frame(train)
    pipeline.fit(prepared.loc[:, list(APPROVED_NAMES)], prepared[LABEL_COLUMN].to_numpy())
    before = positive_scores(pipeline, prepared).tolist()
    joblib.dump(pipeline, reference)
    output_dir = tmp_path / "phase6-v1"
    frozen = select_from_frame(
        frame,
        reference_path=reference,
        output_dir=output_dir,
        provenance={"source_sha256": "abc", "feature_spec_version": SPEC_VERSION},
        cv_splits=2,
    )
    assert frozen["test_year_scored"] is False
    assert not (output_dir / "test-evaluation.json").exists()
    assert frozen["decision_sha256"] == decision_hash(frozen["decision"])
    assert frozen["decision"]["positive_codes"] == ["1", "2"]
    assert frozen["decision"]["negative_codes"] == ["3"]
    assert frozen["decision"]["test_used_for_selection"] is False
    assert file_sha256(reference) == frozen["decision"]["reference_artifact_sha256"]
    reloaded = load_estimator(reference)
    assert positive_scores(reloaded, prepared).tolist() == before
    with pytest.raises(DataError, match="Phase 5"):
        select_from_frame(
            frame,
            reference_path=reference,
            output_dir=tmp_path / "baselines-v1",
            provenance={"source_sha256": "abc"},
            cv_splits=2,
        )


def test_evaluation_scores_2025_once_and_checks_the_frozen_files(tmp_path: Path) -> None:
    frame = _population()
    output_dir = _freeze(tmp_path, frame)
    provenance = {"source_sha256": "abc", "feature_spec_version": SPEC_VERSION}
    evaluation = evaluate_frozen(frame, output_dir=output_dir, provenance=provenance)
    assert evaluation["rows"] == 2
    assert evaluation["positive_rows"] == 1
    assert evaluation["test_used_for_selection"] is False
    matrix = evaluation["metrics"]["confusion_matrix"]["matrix"]
    assert sum(sum(row) for row in matrix) == 2
    result = output_dir / "test-evaluation.json"
    first_bytes = result.read_bytes()
    with pytest.raises(DataError, match="already been scored"):
        evaluate_frozen(frame, output_dir=output_dir, provenance=provenance)
    assert result.read_bytes() == first_bytes
    with pytest.raises(DataError, match="already been scored"):
        select_from_frame(
            frame,
            reference_path=tmp_path / "hist_gradient_boosting.joblib",
            output_dir=output_dir,
            provenance=provenance,
            cv_splits=2,
        )
    assert result.read_bytes() == first_bytes


def test_evaluation_rejects_a_tampered_or_incompatible_artifact(tmp_path: Path) -> None:
    frame = _population()
    output_dir = _freeze(tmp_path, frame)
    provenance = {"source_sha256": "abc", "feature_spec_version": SPEC_VERSION}
    frozen_path = output_dir / "frozen-config.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    frozen["decision"]["threshold"] = 0.2
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(DataError, match="hash"):
        evaluate_frozen(frame, output_dir=output_dir, provenance=provenance)
    frozen["decision"]["threshold"] = 0
    frozen["decision_sha256"] = decision_hash(frozen["decision"])
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(DataError, match="threshold"):
        evaluate_frozen(frame, output_dir=output_dir, provenance=provenance)

    output_dir = _freeze(tmp_path / "second", frame)
    frozen_path = output_dir / "frozen-config.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    replacement = output_dir / "selected-pipeline.joblib"
    joblib.dump({"not": "a model"}, replacement)
    frozen["decision"]["selected_artifact_sha256"] = file_sha256(replacement)
    frozen["decision_sha256"] = decision_hash(frozen["decision"])
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(DataError, match="probability"):
        evaluate_frozen(frame, output_dir=output_dir, provenance=provenance)

    missing = tmp_path / "missing"
    missing.mkdir()
    with pytest.raises(DataError, match="missing"):
        evaluate_frozen(frame, output_dir=missing, provenance=provenance)


def test_evaluation_rejects_a_different_feature_spec_before_opening_2025(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def opened(*_args, **_kwargs):
        raise AssertionError("test split opened after a spec mismatch")

    monkeypatch.setattr("roadrisk.training.phase6.held_out_rows", opened)
    frame = _population()
    output_dir = _freeze(tmp_path, frame)
    with pytest.raises(FeatureContractError, match="Feature spec"):
        evaluate_frozen(
            frame,
            output_dir=output_dir,
            provenance={"source_sha256": "abc", "feature_spec_version": 99},
        )


def test_validation_functions_require_the_2024_split_only() -> None:
    cases = [
        pd.DataFrame(columns=["collision_year", "split", LABEL_COLUMN]),
        _year_rows([("2022", "training", 0)]),
        _year_rows([("2024", "validation", 0), ("2023", "validation", 1)]),
        _year_rows([("2025", "test", 1)]),
        _year_rows([("2024", "training", 0)]),
    ]
    for frame in cases:
        with pytest.raises(FeatureContractError):
            choose_threshold_on_validation(frame, [0.2] * max(len(frame), 1))
        with pytest.raises(FeatureContractError):
            score_fitted_candidates(object(), {}, frame)


def test_empty_or_malformed_evaluation_lock_is_rejected(tmp_path: Path) -> None:
    output_dir = _write_lock(tmp_path / "empty")
    result = output_dir / "test-evaluation.json"
    frozen = output_dir / "frozen-config.json"
    before_frozen = frozen.read_bytes()
    result.write_text("", encoding="utf-8")
    with pytest.raises(DataError, match="evaluation lock is invalid"):
        refuse_existing_evaluation(output_dir)
    assert frozen.read_bytes() == before_frozen
    assert result.read_text(encoding="utf-8") == ""

    output_dir = _write_lock(tmp_path / "malformed")
    result = output_dir / "test-evaluation.json"
    frozen = output_dir / "frozen-config.json"
    before_frozen = frozen.read_bytes()
    result.write_text("{", encoding="utf-8")
    with pytest.raises(DataError, match="evaluation lock is invalid"):
        refuse_existing_evaluation(output_dir)
    assert result.read_bytes() == b"{"
    assert frozen.read_bytes() == before_frozen


def test_valid_lock_refuses_before_the_feature_table_is_loaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = _write_lock(tmp_path)
    before_result = (output_dir / "test-evaluation.json").read_bytes()
    before_frozen = (output_dir / "frozen-config.json").read_bytes()

    def opened(*_args, **_kwargs):
        raise AssertionError("feature loading or test scoring was called")

    monkeypatch.setattr(training_main, "load_feature_table", opened)
    monkeypatch.setattr(training_main, "verify_collision_file", opened)
    monkeypatch.setattr("roadrisk.training.phase6.held_out_rows", opened)
    monkeypatch.setattr("roadrisk.training.phase6.positive_scores", opened)
    with pytest.raises(DataError, match="already been scored"):
        training_main._evaluate(
            tmp_path,
            Path("configs/data_manifest.json"),
            tmp_path / "missing.csv",
            output_dir,
            tmp_path,
        )
    assert (output_dir / "test-evaluation.json").read_bytes() == before_result
    assert (output_dir / "frozen-config.json").read_bytes() == before_frozen


def test_mismatched_decision_hash_is_an_invalid_lock(tmp_path: Path) -> None:
    output_dir = _write_lock(tmp_path)
    result = output_dir / "test-evaluation.json"
    frozen = output_dir / "frozen-config.json"
    before_frozen = frozen.read_bytes()
    payload = json.loads(result.read_text(encoding="utf-8"))
    payload["decision_sha256"] = "0" * 64
    result.write_text(json.dumps(payload), encoding="utf-8")
    rewritten = result.read_bytes()
    with pytest.raises(DataError, match="evaluation lock is invalid"):
        refuse_existing_evaluation(output_dir)
    assert result.read_bytes() == rewritten
    assert frozen.read_bytes() == before_frozen


def test_inconsistent_confusion_matrix_is_an_invalid_lock(tmp_path: Path) -> None:
    output_dir = _write_lock(tmp_path)
    result = output_dir / "test-evaluation.json"
    frozen = output_dir / "frozen-config.json"
    before_frozen = frozen.read_bytes()
    payload = json.loads(result.read_text(encoding="utf-8"))
    payload["metrics"]["confusion_matrix"]["matrix"] = [[1, 0], [0, 1]]
    result.write_text(json.dumps(payload), encoding="utf-8")
    rewritten = result.read_bytes()
    with pytest.raises(DataError, match="Confusion-matrix counts"):
        refuse_existing_evaluation(output_dir)
    assert result.read_bytes() == rewritten
    assert frozen.read_bytes() == before_frozen


def test_saved_phase6_lock_is_accepted_without_rewriting() -> None:
    output_dir = Path("data/models/phase6-v1")
    result = output_dir / "test-evaluation.json"
    frozen = output_dir / "frozen-config.json"
    if not result.is_file() or not frozen.is_file():
        pytest.skip("saved Phase 6 evaluation is not in this checkout")
    before_result = result.read_bytes()
    before_frozen = frozen.read_bytes()
    with pytest.raises(DataError, match="already been scored"):
        refuse_existing_evaluation(output_dir)
    assert result.read_bytes() == before_result
    assert frozen.read_bytes() == before_frozen


def test_load_estimator_rejects_missing_and_non_model_files(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="missing"):
        load_estimator(tmp_path / "absent.joblib")
    path = tmp_path / "notes.joblib"
    joblib.dump({"not": "a model"}, path)
    with pytest.raises(DataError, match="probability"):
        load_estimator(path)


def _year_rows(rows: list[tuple[str, str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "collision_year": [year for year, _split, _label in rows],
            "split": [split for _year, split, _label in rows],
            LABEL_COLUMN: [label for _year, _split, label in rows],
        }
    )


def _write_lock(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    decision = {key: f"recorded-{key}" for key in DECISION_KEYS}
    decision.update(
        {
            "phase": 6,
            "model": "hist_gradient_boosting",
            "calibration_method": "sigmoid",
            "calibration_ensemble": False,
            "calibration_cv_splits": 3,
            "calibration_cv_shuffle": True,
            "random_seed": 42,
            "threshold": 0.15,
            "threshold_reference": 0.5,
            "threshold_f1_margin": 0.01,
            "feature_spec_version": SPEC_VERSION,
            "source_sha256": "abc",
            "positive_codes": ["1", "2"],
            "negative_codes": ["3"],
            "positive_label": 1,
            "negative_label": 0,
            "training_period": ["2021", "2022", "2023"],
            "validation_period": ["2024"],
            "test_period": ["2025"],
            "test_used_for_selection": False,
            "validation_metrics_are_selection_results": True,
        }
    )
    metrics = positive_class_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], threshold=0.15)
    frozen = {
        "decision": decision,
        "decision_sha256": decision_hash(decision),
        "test_year_scored": False,
    }
    evaluation = {
        "decision_sha256": frozen["decision_sha256"],
        "model": decision["model"],
        "calibration_method": decision["calibration_method"],
        "threshold": decision["threshold"],
        "feature_spec_version": decision["feature_spec_version"],
        "source_sha256": decision["source_sha256"],
        "rows": metrics["rows"],
        "positive_rows": metrics["positive_rows"],
        "period": "2025",
        "test_used_for_selection": False,
        "metrics": metrics,
    }
    (directory / "frozen-config.json").write_text(json.dumps(frozen), encoding="utf-8")
    (directory / "test-evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    return directory


def _candidate(method: str, *, brier: float, log_loss: float, average_precision: float) -> dict:
    return {
        "method": method,
        "metrics": {
            "brier": brier,
            "log_loss": log_loss,
            "average_precision": average_precision,
        },
    }


def _freeze(tmp_path: Path, frame: pd.DataFrame) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    train, _validation, _test_rows = training_and_validation(frame)
    reference = tmp_path / "hist_gradient_boosting.joblib"
    pipeline = make_baseline("logistic_regression")
    prepared = normalize_model_frame(train)
    pipeline.fit(prepared.loc[:, list(APPROVED_NAMES)], prepared[LABEL_COLUMN].to_numpy())
    joblib.dump(pipeline, reference)
    output_dir = tmp_path / "phase6-v1"
    select_from_frame(
        frame,
        reference_path=reference,
        output_dir=output_dir,
        provenance={"source_sha256": "abc", "feature_spec_version": SPEC_VERSION},
        cv_splits=2,
    )
    return output_dir


def _population() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(8):
        rows.append(
            {
                "collision_year": "2022",
                "split": "training",
                LABEL_COLUMN: index % 2,
                "longitude": str(index),
            }
        )
    for index, label in enumerate((0, 1, 0, 1)):
        rows.append(
            {
                "collision_year": "2024",
                "split": "validation",
                LABEL_COLUMN: label,
                "longitude": str(index + 0.5),
            }
        )
    rows.append({"collision_year": "2025", "split": "test", LABEL_COLUMN: 1, "longitude": "9"})
    rows.append({"collision_year": "2025", "split": "test", LABEL_COLUMN: 0, "longitude": "8"})
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
            }
        )
        row.update(overrides)
        records.append(row)
    return pd.DataFrame.from_records(records)
