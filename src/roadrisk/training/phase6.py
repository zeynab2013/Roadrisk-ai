"""Freeze calibration and threshold choices, then score 2025 once.

Selection reads training and validation rows only. The test split is opened
by ``evaluate_frozen`` after ``frozen-config.json`` exists. A valid
``test-evaluation.json`` blocks another score. The check is local: deleting
or replacing that file and the frozen decision removes the record. It is
not a tamper-proof seal.

``frozen-config.json`` stays the pre-test decision snapshot. Its
``test_year_scored`` value is the state when that file was created.
``test-evaluation.json`` is the completed test record.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections.abc import Mapping
from pathlib import Path

import joblib
import pandas as pd

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.features.spec import SPEC_VERSION
from roadrisk.training.calibration import (
    CALIBRATION_METHODS,
    choose_calibration,
    fit_calibrator,
    score_fitted_candidates,
)
from roadrisk.training.columns import LABEL_COLUMN
from roadrisk.training.metrics import assert_metric_consistency, positive_class_metrics
from roadrisk.training.pipelines import SEED, make_baseline
from roadrisk.training.population import held_out_rows, training_and_validation
from roadrisk.training.run import normalize_model_frame, utc_now
from roadrisk.training.scoring import load_estimator, positive_scores
from roadrisk.training.threshold import choose_threshold_on_validation

logger = logging.getLogger(__name__)

PHASE6_DIR_NAME = "phase6-v1"
REFERENCE_MODEL = "hist_gradient_boosting"
REFERENCE_ARTIFACT = "hist_gradient_boosting.joblib"
SELECTED_ARTIFACT = "selected-pipeline.joblib"
FROZEN_CONFIG = "frozen-config.json"
CALIBRATION_COMPARISON = "calibration-comparison.json"
THRESHOLD_COMPARISON = "threshold-comparison.json"
TEST_EVALUATION = "test-evaluation.json"
BASELINE_DIR_NAME = "baselines-v1"

QUESTION = "Given a reported personal-injury collision, was it fatal or serious rather than slight?"
NOT_ESTIMATED = "Whether a collision occurs."

DECISION_KEYS = (
    "phase",
    "question",
    "not_estimated",
    "model",
    "calibration_method",
    "calibration_fitted_on",
    "calibration_cv_splits",
    "calibration_ensemble",
    "calibration_cv_shuffle",
    "random_seed",
    "threshold",
    "threshold_reference",
    "threshold_objective",
    "threshold_f1_margin",
    "feature_spec_version",
    "source_sha256",
    "positive_codes",
    "negative_codes",
    "positive_label",
    "negative_label",
    "training_period",
    "validation_period",
    "test_period",
    "test_used_for_selection",
    "reference_artifact",
    "reference_artifact_sha256",
    "selected_artifact",
    "selected_artifact_sha256",
    "calibration_comparison_sha256",
    "threshold_comparison_sha256",
    "selection_rule_calibration",
    "selection_rule_threshold",
    "chosen_because",
    "validation_metrics_are_selection_results",
)


def select_from_frame(
    frame: pd.DataFrame,
    *,
    reference_path: Path,
    output_dir: Path,
    provenance: Mapping[str, object],
    cv_splits: int = 3,
) -> dict[str, object]:
    """Choose calibration and a threshold, then write the frozen configuration.

    ``frame`` may contain 2025 rows. This function does not score them.
    """

    _assert_output_is_separate(output_dir)
    refuse_existing_evaluation(output_dir)
    if not reference_path.is_file():
        raise DataError(f"Phase 5 reference model is missing: {reference_path}")
    prepared = normalize_model_frame(frame)
    _require_binary_labels(prepared)
    train, validation, test_rows = training_and_validation(prepared)
    reference = load_estimator(reference_path)
    logger.info("Scoring the uncalibrated Phase 5 model on 2024")
    calibrated: dict[str, object] = {}
    for method in CALIBRATION_METHODS:
        logger.info("Fitting %s calibration with %s training folds", method, cv_splits)
        calibrated[method] = fit_calibrator(
            make_baseline(REFERENCE_MODEL),
            train,
            method=method,
            cv_splits=cv_splits,
        )
    candidates = score_fitted_candidates(reference, calibrated, validation)
    calibration_choice = choose_calibration(candidates)
    method = str(calibration_choice["method"])
    if method == "none":
        estimator = reference
    else:
        estimator = calibrated[method]
    logger.info("Selecting a threshold from 2024 scores of method %s", method)
    scores = positive_scores(estimator, validation)
    threshold_choice = choose_threshold_on_validation(validation, scores)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_path = output_dir / SELECTED_ARTIFACT
    if method == "none":
        shutil.copy2(reference_path, selected_path)
    else:
        joblib.dump(estimator, selected_path)
    calibration_payload = {
        "comparison_period": "2024",
        "used_for": "calibration method selection",
        "independent_estimate": False,
        "candidates": [_public_candidate(row) for row in candidates],
        "choice": calibration_choice,
    }
    threshold_payload = {
        "comparison_period": "2024",
        "used_for": "threshold selection",
        "independent_estimate": False,
        "probability_method": method,
        "choice": {key: value for key, value in threshold_choice.items() if key != "grid"},
        "grid": threshold_choice["grid"],
    }
    _write_json(output_dir / CALIBRATION_COMPARISON, calibration_payload)
    _write_json(output_dir / THRESHOLD_COMPARISON, threshold_payload)
    decision = _decision(
        provenance=provenance,
        reference_path=reference_path,
        selected_path=selected_path,
        calibration_path=output_dir / CALIBRATION_COMPARISON,
        threshold_path=output_dir / THRESHOLD_COMPARISON,
        calibration_choice=calibration_choice,
        threshold_choice=threshold_choice,
        cv_splits=cv_splits,
    )
    frozen = {
        "decision": decision,
        "decision_sha256": decision_hash(decision),
        "test_rows_held_out": test_rows,
        "test_year_scored": False,
        "created_at": utc_now(),
        "note": (
            "2024 metrics chose the calibration method and the threshold. "
            "They are model-selection results, not an unbiased estimate of future performance. "
            "2025 has not been scored."
        ),
    }
    _write_json(output_dir / FROZEN_CONFIG, frozen)
    selection_note = render_selection(frozen, calibration_payload, threshold_payload)
    (output_dir / "selection.md").write_text(selection_note, encoding="utf-8")
    logger.info("Frozen configuration: %s", output_dir / FROZEN_CONFIG)
    logger.info("Held out %s test rows without scoring them", test_rows)
    return frozen


def evaluate_frozen(
    frame: pd.DataFrame,
    *,
    output_dir: Path,
    provenance: Mapping[str, object],
) -> dict[str, object]:
    """Score the frozen pipeline on 2025 once. Refuses a second score."""

    refuse_existing_evaluation(output_dir)
    frozen_path = output_dir / FROZEN_CONFIG
    if not frozen_path.is_file():
        raise DataError(f"Frozen configuration is missing: {frozen_path}")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if not isinstance(frozen, dict):
        raise DataError("Frozen configuration must be a JSON object")
    decision = _require_mapping(frozen.get("decision"), "decision")
    _validate_decision(decision, expected_hash=str(frozen.get("decision_sha256")))
    _require_file_hash(
        output_dir / str(decision["selected_artifact"]), decision["selected_artifact_sha256"]
    )
    _require_file_hash(
        output_dir / CALIBRATION_COMPARISON,
        decision["calibration_comparison_sha256"],
    )
    _require_file_hash(
        output_dir / THRESHOLD_COMPARISON,
        decision["threshold_comparison_sha256"],
    )
    if provenance.get("source_sha256") != decision["source_sha256"]:
        raise FeatureContractError("Collision checksum does not match the frozen configuration")
    if provenance.get("feature_spec_version") != decision["feature_spec_version"]:
        raise FeatureContractError("Feature spec version does not match the frozen configuration")
    estimator = load_estimator(output_dir / str(decision["selected_artifact"]))
    prepared = normalize_model_frame(frame)
    _require_binary_labels(prepared)
    held_out = held_out_rows(prepared)
    labels = held_out[LABEL_COLUMN].to_numpy()
    scores = positive_scores(estimator, held_out)
    metrics = positive_class_metrics(labels, scores, threshold=float(decision["threshold"]))
    assert_metric_consistency(metrics)
    evaluation = {
        "question": QUESTION,
        "not_estimated": NOT_ESTIMATED,
        "period": "2025",
        "decision_sha256": frozen["decision_sha256"],
        "model": decision["model"],
        "calibration_method": decision["calibration_method"],
        "threshold": decision["threshold"],
        "feature_spec_version": decision["feature_spec_version"],
        "source_sha256": decision["source_sha256"],
        "selected_artifact_sha256": decision["selected_artifact_sha256"],
        "rows": metrics["rows"],
        "positive_rows": metrics["positive_rows"],
        "evaluated_at": utc_now(),
        "test_used_for_selection": False,
        "metrics": metrics,
        "limitation": (
            "Beating a dummy baseline on this extract does not show that the model "
            "is reliable for road-safety decisions. Discrimination on this task is modest, "
            "the classes are uneven, and reporting practice can shift over time."
        ),
    }
    result_path = output_dir / TEST_EVALUATION
    _write_json(result_path, evaluation)
    (output_dir / "test-evaluation.md").write_text(
        render_evaluation(evaluation),
        encoding="utf-8",
    )
    logger.info("Scored %s test rows once", metrics["rows"])
    return evaluation


def decision_hash(decision: Mapping[str, object]) -> str:
    """SHA-256 of the canonical decision object."""

    payload = {key: decision[key] for key in DECISION_KEYS}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_selection(frozen, calibration_payload, threshold_payload) -> str:
    """Markdown for the 2024 selection. It does not contain 2025 scores."""

    decision = frozen["decision"]
    lines = [
        "# Phase 6 selection",
        "",
        QUESTION,
        "",
        "These 2024 figures chose the calibration method and the threshold.",
        "They are not an unbiased estimate of future performance.",
        "The 2025 test year was not scored.",
        "The model does not estimate whether a collision occurs.",
        "",
        f"Model: `{decision['model']}`.",
        f"Calibration: `{decision['calibration_method']}`.",
        f"Threshold: `{decision['threshold']}`. The 0.5 reference is retained in the grid.",
        "",
        decision["chosen_because"],
        "",
        "## Calibration on 2024",
        "",
        "| Method | Average precision | ROC-AUC | Brier | Log loss | ECE |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in calibration_payload["candidates"]:
        metrics = row["metrics"]
        reliability = row["reliability"]
        lines.append(
            "| "
            f"{row['method']} | {_num(metrics.get('average_precision'))} | "
            f"{_num(metrics.get('roc_auc'))} | {_num(metrics.get('brier'))} | "
            f"{_num(metrics.get('log_loss'))} | "
            f"{_num(reliability.get('expected_calibration_error'))} |"
        )
    lines.extend(["", "## Selected threshold on 2024", ""])
    selected = threshold_payload["choice"]["selected_metrics"]
    lines.extend(_metric_lines(selected))
    lines.extend(
        [
            "",
            "Accuracy is reported and is not the selection metric.",
            "",
            f"Decision SHA-256: `{frozen['decision_sha256']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def render_evaluation(evaluation: Mapping[str, object]) -> str:
    """Markdown for the single 2025 score."""

    metrics = _require_mapping(evaluation.get("metrics"), "metrics")
    lines = [
        "# Phase 6 test evaluation",
        "",
        str(evaluation.get("question")),
        "",
        "This is the 2025 test score of the frozen pipeline.",
        "2025 was not used to choose the model, the calibration method, or the threshold.",
        "The model does not estimate whether a collision occurs.",
        "",
        f"Model: `{evaluation.get('model')}`.",
        f"Calibration: `{evaluation.get('calibration_method')}`.",
        f"Threshold: `{evaluation.get('threshold')}`.",
        f"Rows: {evaluation.get('rows')}. Positive rows: {evaluation.get('positive_rows')}.",
        f"Evaluated at: {evaluation.get('evaluated_at')}.",
        f"Decision SHA-256: `{evaluation.get('decision_sha256')}`.",
        "",
        *(_metric_lines(metrics)),
        "",
        str(evaluation.get("limitation")),
        "",
    ]
    return "\n".join(lines)


def _decision(
    *,
    provenance: Mapping[str, object],
    reference_path: Path,
    selected_path: Path,
    calibration_path: Path,
    threshold_path: Path,
    calibration_choice: Mapping[str, object],
    threshold_choice: Mapping[str, object],
    cv_splits: int,
) -> dict[str, object]:
    method = str(calibration_choice["method"])
    threshold = float(threshold_choice["threshold"])
    return {
        "phase": 6,
        "question": QUESTION,
        "not_estimated": NOT_ESTIMATED,
        "model": REFERENCE_MODEL,
        "calibration_method": method,
        "calibration_fitted_on": (
            "2021-2023 out-of-fold predictions from CalibratedClassifierCV. "
            "The calibrator was not fit on 2024 or 2025. "
            "The uncalibrated candidate is the unmodified Phase 5 artifact."
        ),
        "calibration_cv_splits": cv_splits,
        "calibration_ensemble": False,
        "calibration_cv_shuffle": True,
        "random_seed": SEED,
        "threshold": threshold,
        "threshold_reference": 0.5,
        "threshold_objective": threshold_choice["objective"],
        "threshold_f1_margin": threshold_choice["f1_improvement_margin"],
        "feature_spec_version": SPEC_VERSION,
        "source_sha256": provenance["source_sha256"],
        "positive_codes": ["1", "2"],
        "negative_codes": ["3"],
        "positive_label": 1,
        "negative_label": 0,
        "training_period": ["2021", "2022", "2023"],
        "validation_period": ["2024"],
        "test_period": ["2025"],
        "test_used_for_selection": False,
        "reference_artifact": REFERENCE_ARTIFACT,
        "reference_artifact_sha256": file_sha256(reference_path),
        "selected_artifact": SELECTED_ARTIFACT,
        "selected_artifact_sha256": file_sha256(selected_path),
        "calibration_comparison_sha256": file_sha256(calibration_path),
        "threshold_comparison_sha256": file_sha256(threshold_path),
        "selection_rule_calibration": calibration_choice["rule"],
        "selection_rule_threshold": threshold_choice["objective"],
        "chosen_because": f"{calibration_choice['reason']} {threshold_choice['reason']}",
        "validation_metrics_are_selection_results": True,
    }


def _validate_decision(decision: Mapping[str, object], *, expected_hash: str) -> None:
    missing = [key for key in DECISION_KEYS if key not in decision]
    if missing:
        raise DataError("Frozen decision is missing: " + ", ".join(missing))
    if decision_hash(decision) != expected_hash:
        raise DataError("Frozen decision hash does not match the configuration")
    if decision["phase"] != 6 or decision["model"] != REFERENCE_MODEL:
        raise DataError(
            "Frozen decision does not name the Phase 6 histogram gradient boosting model"
        )
    if decision["feature_spec_version"] != SPEC_VERSION:
        raise FeatureContractError(
            f"Feature spec version is {decision['feature_spec_version']}, expected {SPEC_VERSION}"
        )
    if decision["positive_codes"] != ["1", "2"] or decision["negative_codes"] != ["3"]:
        raise FeatureContractError("Frozen decision changes the severity class definition")
    if decision["positive_label"] != 1 or decision["negative_label"] != 0:
        raise FeatureContractError("Frozen decision changes the label encoding")
    if decision["test_used_for_selection"] is not False:
        raise FeatureContractError("Frozen decision says 2025 was used for selection")
    if decision["test_period"] != ["2025"] or decision["validation_period"] != ["2024"]:
        raise FeatureContractError("Frozen decision changes the temporal split")
    method = decision["calibration_method"]
    if method not in {"none", *CALIBRATION_METHODS}:
        raise DataError(f"Frozen calibration method is not supported: {method}")
    threshold = decision["threshold"]
    if not isinstance(threshold, (int, float)) or not (0.0 < float(threshold) <= 1.0):
        raise DataError("Frozen threshold must be finite and in the interval (0, 1]")
    if decision["calibration_ensemble"] is not False:
        raise DataError("Frozen calibration must use out-of-fold predictions, not an ensemble")


def _assert_output_is_separate(output_dir: Path) -> None:
    if output_dir.name == BASELINE_DIR_NAME:
        raise DataError("Phase 6 must not write into the Phase 5 baseline directory")


def refuse_existing_evaluation(output_dir: Path) -> None:
    """Read a saved test result without scoring or rewriting it.

    No ``test-evaluation.json`` means the caller may score. A result that
    matches the frozen decision raises ``DataError`` and names the completed
    evaluation. An unreadable, inconsistent, or mismatched file raises a
    different ``DataError`` and is left in place. Removing the local files
    removes this lock.
    """

    result_path = output_dir / TEST_EVALUATION
    if not result_path.is_file():
        return
    evaluation = _read_json_object(result_path)
    frozen_path = output_dir / FROZEN_CONFIG
    frozen = _read_json_object(frozen_path)
    if evaluation is None or frozen is None:
        raise DataError(
            "The evaluation lock is invalid. test-evaluation.json or "
            "frozen-config.json is unreadable or not a JSON object. "
            "Refusing to score again."
        )
    decision = frozen.get("decision")
    if not isinstance(decision, Mapping):
        raise DataError(
            "The evaluation lock is invalid. The frozen decision is missing. "
            "Refusing to score again."
        )
    try:
        _validate_decision(decision, expected_hash=str(frozen.get("decision_sha256")))
    except DataError as exc:
        raise DataError(
            "The evaluation lock is invalid. The frozen decision could not be checked. "
            f"{exc} Refusing to score again."
        ) from exc
    _require_matching_evaluation(evaluation, decision, str(frozen.get("decision_sha256")))
    raise DataError(
        "2025 has already been scored for this directory. "
        "The saved test-evaluation.json matches the frozen decision. "
        "Refusing another score."
    )


def _read_json_object(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _require_matching_evaluation(
    evaluation: Mapping[str, object],
    decision: Mapping[str, object],
    decision_sha256: str,
) -> None:
    required = (
        "decision_sha256",
        "model",
        "calibration_method",
        "threshold",
        "feature_spec_version",
        "source_sha256",
        "rows",
        "positive_rows",
        "period",
        "test_used_for_selection",
        "metrics",
    )
    missing = [key for key in required if key not in evaluation]
    if missing:
        raise DataError(
            "The evaluation lock is invalid. The saved result is missing: "
            + ", ".join(missing)
            + ". Refusing to score again."
        )
    if evaluation["decision_sha256"] != decision_sha256:
        raise DataError(
            "The evaluation lock is invalid. Its decision hash does not match "
            "the frozen decision. Refusing to score again."
        )
    compared = {
        "model": decision["model"],
        "calibration_method": decision["calibration_method"],
        "threshold": decision["threshold"],
        "feature_spec_version": decision["feature_spec_version"],
        "source_sha256": decision["source_sha256"],
    }
    for key, expected in compared.items():
        if evaluation[key] != expected:
            raise DataError(
                "The evaluation lock is invalid. "
                f"{key} does not match the frozen decision. Refusing to score again."
            )
    if evaluation["period"] != "2025" or evaluation["test_used_for_selection"] is not False:
        raise DataError(
            "The evaluation lock is invalid. The saved result does not describe "
            "one untouched 2025 score. Refusing to score again."
        )
    metrics = evaluation["metrics"]
    if not isinstance(metrics, Mapping):
        raise DataError(
            "The evaluation lock is invalid. The saved metrics are missing. "
            "Refusing to score again."
        )
    if evaluation["rows"] != metrics.get("rows") or evaluation["positive_rows"] != metrics.get(
        "positive_rows"
    ):
        raise DataError(
            "The evaluation lock is invalid. Confusion-matrix counts do not match "
            "the stored totals. Refusing to score again."
        )
    try:
        assert_metric_consistency(metrics)
    except ValueError as exc:
        raise DataError(
            "The evaluation lock is invalid. Confusion-matrix counts do not match "
            f"the stored totals. {exc} Refusing to score again."
        ) from exc


def _require_binary_labels(frame: pd.DataFrame) -> None:
    labels = set(frame[LABEL_COLUMN].astype(int))
    if not labels <= {0, 1}:
        raise FeatureContractError("severity_serious_or_fatal must contain only 0 and 1")


def _public_candidate(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "method": row["method"],
        "metrics": row["metrics"],
        "reliability": row["reliability"],
    }


def _require_file_hash(path: Path, expected: object) -> None:
    if not path.is_file():
        raise DataError(f"Frozen artifact is missing: {path}")
    if file_sha256(path) != expected:
        raise DataError(f"Frozen artifact hash does not match the configuration: {path.name}")


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise DataError(f"Frozen configuration is missing {label}")
    return value


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _metric_lines(metrics: Mapping[str, object]) -> list[str]:
    matrix = metrics["confusion_matrix"]
    assert isinstance(matrix, Mapping)
    return [
        f"Precision: {_num(metrics.get('precision'))}.",
        f"Recall: {_num(metrics.get('recall'))}.",
        f"F1: {_num(metrics.get('f1'))}.",
        f"Accuracy: {_num(metrics.get('accuracy'))}. Accuracy is not the selection metric.",
        f"Average precision: {_num(metrics.get('average_precision'))}.",
        f"ROC-AUC: {_num(metrics.get('roc_auc'))}.",
        f"Brier: {_num(metrics.get('brier'))}.",
        f"Log loss: {_num(metrics.get('log_loss'))}.",
        f"Predicted positive: {metrics.get('predicted_positive')}.",
        f"Confusion matrix (true rows, predicted columns): {matrix.get('matrix')}.",
    ]


def _num(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.4f}"
    return "undefined"
