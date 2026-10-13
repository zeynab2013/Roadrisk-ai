"""Fit the four baselines and score 2024 only."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.data.manifest import load_manifest, resolve_path
from roadrisk.data.validate import file_status
from roadrisk.features.spec import APPROVED_NAMES, SPEC_VERSION
from roadrisk.training.columns import CATEGORICAL_FEATURES, LABEL_COLUMN, NUMERIC_FEATURES
from roadrisk.training.metrics import choose_provisional, positive_class_metrics
from roadrisk.training.pipelines import BASELINE_SETTINGS, baseline_names, make_baseline
from roadrisk.training.report import render_comparison

logger = logging.getLogger(__name__)
MODEL_DIR_NAME = "baselines-v1"


def load_feature_table(path: Path) -> pd.DataFrame:
    """Read the Phase 4 feature CSV. Numeric blanks become missing values."""

    if not path.is_file():
        raise DataError(f"Feature table is missing: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame = normalize_model_frame(frame)
    labels = set(frame[LABEL_COLUMN].astype(str))
    if not labels <= {"0", "1"}:
        raise FeatureContractError("severity_serious_or_fatal must contain only 0 and 1")
    frame[LABEL_COLUMN] = frame[LABEL_COLUMN].astype(int)
    return frame


def assert_feature_provenance(meta: Mapping[str, object], *, sha256: str) -> None:
    """Stop when the feature table was not built from this manifest and spec."""

    if meta.get("feature_spec_version") != SPEC_VERSION:
        raise FeatureContractError(
            f"Feature spec version is {meta.get('feature_spec_version')}, expected {SPEC_VERSION}"
        )
    source = meta.get("source")
    if not isinstance(source, Mapping) or source.get("sha256") != sha256:
        raise FeatureContractError("Feature table checksum does not match the collision manifest")
    columns = meta.get("model_input_columns")
    if list(columns) != list(APPROVED_NAMES):
        raise FeatureContractError("Feature table model inputs do not match the approved allowlist")


def fit_baselines(train: pd.DataFrame, validation: pd.DataFrame) -> list[dict[str, object]]:
    """Fit each baseline on training rows and score validation rows."""

    from roadrisk.training.population import assert_excludes_test

    assert_excludes_test(train, purpose="training")
    assert_excludes_test(validation, purpose="validation")
    train = normalize_model_frame(train)
    validation = normalize_model_frame(validation)
    fitted = []
    for name in baseline_names():
        logger.info("Fitting %s on %s training rows", name, len(train))
        pipeline = make_baseline(name)
        pipeline.fit(_inputs(train), train[LABEL_COLUMN].to_numpy())
        logger.info("Scoring %s on %s validation rows", name, len(validation))
        scores = _positive_scores(pipeline, validation)
        metrics = positive_class_metrics(validation[LABEL_COLUMN].to_numpy(), scores)
        fitted.append(
            {
                "model": name,
                "settings": BASELINE_SETTINGS[name],
                "metrics": metrics,
                "pipeline": pipeline,
            }
        )
    return fitted


def save_run(
    fitted: list[dict[str, object]],
    output_dir: Path,
    *,
    provenance: Mapping[str, object],
) -> dict[str, object]:
    """Write pipelines, metrics, and the comparison note. Returns the summary."""

    output_dir.mkdir(parents=True, exist_ok=True)
    public = []
    for row in fitted:
        name = str(row["model"])
        artifact = output_dir / f"{name}.joblib"
        joblib.dump(row["pipeline"], artifact)
        public.append(
            {
                "model": name,
                "settings": row["settings"],
                "metrics": row["metrics"],
                "artifact": artifact.name,
            }
        )
    decision = choose_provisional(public)
    summary = {
        "provisional_model": decision,
        "models": public,
        "provenance": dict(provenance),
        "question": (
            "Given a reported personal-injury collision, was it fatal or serious "
            "rather than slight?"
        ),
        "not_estimated": "Whether a collision occurs.",
        "test_year_scored": False,
    }
    (output_dir / "comparison.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "comparison.md").write_text(render_comparison(summary), encoding="utf-8")
    return summary


def dependency_versions() -> dict[str, str]:
    """Versions that produced a training run."""

    import sys

    import joblib as joblib_module
    import pandas as pandas_module
    import sklearn

    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "pandas": pandas_module.__version__,
        "scikit-learn": sklearn.__version__,
        "joblib": joblib_module.__version__,
    }


def verify_collision_file(data_dir: Path, manifest_path: Path) -> tuple[str, int | None]:
    """Return the manifest checksum after the raw collision file verifies."""

    manifest = load_manifest(manifest_path)
    collisions = next((entry for entry in manifest.files if entry.role == "collisions"), None)
    if collisions is None or collisions.sha256 is None:
        raise DataError("Manifest has no verified collisions file")
    path = resolve_path(data_dir, collisions)
    status = file_status(path, collisions)
    if status.state != "verified":
        raise DataError(
            f"{collisions.id} is {status.state}: {path}. "
            "Training stops when the collision file is missing or the SHA-256 does not match."
        )
    return collisions.sha256, collisions.byte_size


def normalize_model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce model columns. Blank categories become missing values."""

    out = frame.copy()
    for name in NUMERIC_FEATURES:
        if name in out.columns:
            out[name] = pd.to_numeric(out[name], errors="coerce")
    for name in CATEGORICAL_FEATURES:
        if name in out.columns:
            out[name] = out[name].replace("", np.nan)
    return out


def utc_now() -> str:
    """Timestamp with a timezone and no microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _inputs(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[:, list(APPROVED_NAMES)]


def _positive_scores(pipeline, frame: pd.DataFrame) -> np.ndarray:
    probabilities = pipeline.predict_proba(_inputs(frame))
    classes = [int(value) for value in pipeline.named_steps["model"].classes_]
    if 1 not in classes:
        raise FeatureContractError("The fitted model has no positive class to score")
    return np.asarray(probabilities[:, classes.index(1)], dtype=float)
