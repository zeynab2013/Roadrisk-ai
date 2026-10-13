"""Score one reported collision from a frozen artifact.

This module does not import FastAPI. Routes in ``apps/api`` call these
functions. They do not fit a model, and they do not score the 2025 test set.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from roadrisk.config import load_settings
from roadrisk.data.errors import DataError, FeatureLeakageError
from roadrisk.features.spec import APPROVED, APPROVED_NAMES, SPEC_VERSION, require_model_inputs
from roadrisk.inference.artifacts import PHASE7_DIR_NAME, RISK_BANDS_FILE, load_frozen_model
from roadrisk.inference.explain import EXPLANATION_LIMITATION, NOT_ESTIMATED
from roadrisk.inference.risk import assign_category, load_risk_bands
from roadrisk.training.columns import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from roadrisk.training.phase6 import PHASE6_DIR_NAME
from roadrisk.training.run import normalize_model_frame
from roadrisk.training.scoring import positive_scores

FROZEN_ROLE = "frozen_phase6"
FIXTURE_ROLE = "synthetic_test_fixture"
CLASS_LABELS = {0: "slight", 1: "fatal_or_serious"}


class InferenceInputError(DataError):
    """The prediction request is not a valid feature row."""


class ArtifactUnavailable(DataError):
    """The frozen pipeline or the band file cannot be served."""


@dataclass(frozen=True)
class InferenceSession:
    """One read-only model and the band file tied to it."""

    estimator: object
    decision: Mapping[str, object]
    bands: Mapping[str, object]
    decision_sha256: str
    artifact_role: str

    @property
    def model_version(self) -> str:
        return self.decision_sha256

    @property
    def threshold(self) -> float:
        return float(self.decision["threshold"])


def open_session(phase6_dir: Path, bands_path: Path) -> InferenceSession:
    """Load a pipeline and its band file. Missing or mismatched files raise."""

    try:
        estimator, decision = load_frozen_model(phase6_dir)
    except DataError as exc:
        raise ArtifactUnavailable(str(exc)) from exc
    if int(decision.get("feature_spec_version", -1)) != SPEC_VERSION:
        raise ArtifactUnavailable(
            "The artifact feature specification does not match the installed contract"
        )
    frozen_path = phase6_dir / "frozen-config.json"
    frozen = _read_object(frozen_path)
    decision_sha = str(frozen.get("decision_sha256"))
    try:
        bands = load_risk_bands(
            bands_path,
            expected_decision_sha256=decision_sha,
            expected_artifact_sha256=str(decision.get("selected_artifact_sha256")),
        )
    except DataError as exc:
        raise ArtifactUnavailable(str(exc)) from exc
    if float(bands["binary_threshold"]) != float(decision["threshold"]):
        raise ArtifactUnavailable(
            "Risk bands name a different classification threshold than the frozen decision"
        )
    role = _artifact_role(frozen, decision)
    return InferenceSession(
        estimator=estimator,
        decision=decision,
        bands=bands,
        decision_sha256=decision_sha,
        artifact_role=role,
    )


def load_default_session(
    environ: Mapping[str, str] | None = None,
    *,
    project_root: Path | None = None,
) -> InferenceSession:
    """Open the artifact paths selected by the environment."""

    phase6_dir, bands_path = artifact_paths(environ, project_root=project_root)
    return open_session(phase6_dir, bands_path)


def artifact_paths(
    environ: Mapping[str, str] | None = None,
    *,
    project_root: Path | None = None,
) -> tuple[Path, Path]:
    """Resolve the Phase 6 directory and the Phase 7 band file."""

    settings = load_settings(environ, project_root=project_root)
    env = os.environ if environ is None else environ
    phase6_default = settings.data_dir / "models" / PHASE6_DIR_NAME
    bands_default = settings.data_dir / "models" / PHASE7_DIR_NAME / RISK_BANDS_FILE
    phase6 = Path(env.get("ROADRISK_PHASE6_DIR", str(phase6_default)))
    bands = Path(env.get("ROADRISK_BANDS_PATH", str(bands_default)))
    root = settings.project_root
    if not phase6.is_absolute():
        phase6 = root / phase6
    if not bands.is_absolute():
        bands = root / bands
    return phase6, bands


def model_info(session: InferenceSession) -> dict[str, object]:
    """Describe the loaded artifact without scoring a row."""

    threshold = session.threshold
    return {
        "model_version": session.model_version,
        "model": session.decision.get("model"),
        "artifact_role": session.artifact_role,
        "calibration_method": session.decision.get("calibration_method"),
        "question": session.decision.get("question"),
        "not_estimated": session.decision.get("not_estimated"),
        "positive_class": "Fatal or serious (codes 1 and 2), encoded as 1",
        "negative_class": "Slight (code 3), encoded as 0",
        "binary_threshold": threshold,
        "threshold_policy": _threshold_policy(threshold),
        "risk_level_low_below": float(session.bands["low_below"]),
        "risk_level_high_at_or_above": float(session.bands["high_at_or_above"]),
        "risk_level_inclusivity": (
            "LOW if probability < low_below; "
            "MEDIUM if low_below <= probability < high_at_or_above; "
            "HIGH if probability >= high_at_or_above."
        ),
        "risk_levels_are": (
            "Research bands for the model's severity probability. "
            "They are not a safety grade and they are not an exposure-adjusted rate."
        ),
        "feature_spec_version": SPEC_VERSION,
        "features": [
            {"name": field.name, "data_type": field.data_type, "meaning": field.meaning}
            for field in APPROVED
        ],
        "feature_count": len(APPROVED_NAMES),
    }


def predict_one(session: InferenceSession, features: Mapping[str, object]) -> dict[str, object]:
    """Return the calibrated probability, class, and stored band for one row."""

    frame = pd.DataFrame([_feature_row(features)])
    prepared = normalize_model_frame(frame)
    probability = _one_probability(positive_scores(session.estimator, prepared))
    threshold = session.threshold
    predicted = int(probability >= threshold)
    level = assign_category(probability, session.bands)
    return {
        "probability": probability,
        "predicted_class": predicted,
        "predicted_class_label": CLASS_LABELS[predicted],
        "risk_level": level,
        "binary_threshold": threshold,
        "model_version": session.model_version,
        "model": session.decision.get("model"),
        "artifact_role": session.artifact_role,
        "threshold_policy": _threshold_policy(threshold),
        "question": session.decision.get("question"),
        "not_estimated": NOT_ESTIMATED,
        "limitation": EXPLANATION_LIMITATION,
    }


def _feature_row(features: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(features, Mapping):
        raise InferenceInputError("Prediction features must be an object")
    names = list(features)
    try:
        require_model_inputs(names)
    except FeatureLeakageError as exc:
        raise InferenceInputError(str(exc)) from exc
    missing = [name for name in APPROVED_NAMES if name not in features]
    if missing:
        raise InferenceInputError("Prediction is missing features: " + ", ".join(missing))
    numeric = set(NUMERIC_FEATURES)
    categorical = set(CATEGORICAL_FEATURES)
    row: dict[str, object] = {}
    for name in APPROVED_NAMES:
        value = features[name]
        if name in numeric:
            row[name] = _numeric(name, value)
        elif name in categorical:
            row[name] = _categorical(name, value)
        else:
            raise InferenceInputError(f"Feature has no approved type: {name}")
    return row


def _numeric(name: str, value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InferenceInputError(f"{name} must be a number or null")
    number = float(value)
    if not math.isfinite(number):
        raise InferenceInputError(f"{name} must be a finite number")
    return number


def _categorical(name: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InferenceInputError(f"{name} must be a string code or null")
    text = value.strip()
    if text == "":
        return None
    return text


def _one_probability(scores) -> float:
    values = list(scores)
    if len(values) != 1:
        raise DataError("The model did not return one probability")
    probability = float(values[0])
    if not math.isfinite(probability) or probability < 0.0 or probability > 1.0:
        raise DataError("The model returned a probability outside [0, 1]")
    return probability


def _threshold_policy(threshold: float) -> str:
    return (
        f"The fatal-or-serious class is probability >= {threshold}. "
        "LOW, MEDIUM, and HIGH use the stored band boundaries. "
        "Those boundaries are not this classification threshold."
    )


def _artifact_role(frozen: Mapping[str, object], decision: Mapping[str, object]) -> str:
    recorded = frozen.get("artifact_role")
    if recorded == FIXTURE_ROLE:
        return FIXTURE_ROLE
    if decision.get("phase") == 6 and decision.get("model") == "hist_gradient_boosting":
        return FROZEN_ROLE
    if isinstance(recorded, str) and recorded:
        return recorded
    return "not_the_frozen_phase6_model"


def _read_object(path: Path) -> Mapping[str, object]:
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ArtifactUnavailable(f"Frozen configuration is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ArtifactUnavailable("Frozen configuration must be a JSON object")
    return payload
