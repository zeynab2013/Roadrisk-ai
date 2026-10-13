"""HTTP contract for the Phase 8 prediction service.

The scored model in these tests is a synthetic fixture. The real Phase 6
files are only read, and only when they are already on disk.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sklearn")

import joblib
from apps.api.main import create_app
from fastapi.testclient import TestClient
from tests.integration.fixture_estimator import LongitudeFixture

from roadrisk.features.spec import APPROVED_NAMES
from roadrisk.inference.explain import explain_frame
from roadrisk.inference.service import (
    FIXTURE_ROLE,
    ArtifactUnavailable,
    InferenceInputError,
    open_session,
    predict_one,
)
from roadrisk.training.columns import NUMERIC_FEATURES
from roadrisk.training.phase6 import DECISION_KEYS, decision_hash, file_sha256

PROTECTED = (
    "data/models/phase6-v1/frozen-config.json",
    "data/models/phase6-v1/selected-pipeline.joblib",
    "data/models/phase6-v1/test-evaluation.json",
    "data/models/phase6-v1/calibration-comparison.json",
    "data/models/phase6-v1/threshold-comparison.json",
    "data/models/baselines-v1/comparison.json",
    "data/models/baselines-v1/hist_gradient_boosting.joblib",
)


def test_service_module_does_not_import_fastapi() -> None:
    script = (
        "import roadrisk.inference.service, sys; "
        "raise SystemExit(1 if 'fastapi' in sys.modules else 0)"
    )
    completed = subprocess.run([sys.executable, "-c", script], check=False)
    assert completed.returncode == 0


def test_routes_call_the_service_and_do_not_fit() -> None:
    text = Path("apps/api/routes/predictions.py").read_text(encoding="utf-8")
    assert "predict_one" in text
    assert "model_info" in text
    assert "normalize_model_frame" not in text
    assert ".fit(" not in text


def test_health_and_model_report_the_fixture_version(tmp_path: Path) -> None:
    session = _session(tmp_path)
    client = TestClient(create_app(session, database_url=_database_url(tmp_path)))
    health = client.get("/health")
    identity = client.get("/model")
    assert health.status_code == 200
    assert health.json()["ready"] is True
    assert health.json()["model"] == "fixture_not_phase6"
    assert health.json()["artifact_role"] == FIXTURE_ROLE
    assert health.json()["model_version"] == session.model_version
    assert identity.status_code == 200
    body = identity.json()
    assert body["model_version"] == session.model_version
    assert body["artifact_role"] == FIXTURE_ROLE
    assert body["binary_threshold"] == 0.15
    assert body["risk_level_low_below"] == 0.4
    assert body["risk_level_high_at_or_above"] == 0.7
    assert body["feature_count"] == 19
    assert body["not_estimated"] == "Whether a collision occurs."
    assert [item["name"] for item in body["features"]] == list(APPROVED_NAMES)


def test_prediction_uses_the_fixture_threshold_and_bands(tmp_path: Path) -> None:
    session = _session(tmp_path)
    client = TestClient(create_app(session, database_url=_database_url(tmp_path)))
    low = client.post("/predictions", json=_features(longitude=0.149))
    boundary = client.post("/predictions", json=_features(longitude=0.15))
    medium = client.post("/predictions", json=_features(longitude=0.4))
    high = client.post("/predictions", json=_features(longitude=0.7))
    assert low.status_code == 200
    assert low.json()["predicted_class"] == 0
    assert low.json()["risk_level"] == "LOW"
    assert boundary.json()["predicted_class"] == 1
    assert boundary.json()["risk_level"] == "LOW"
    assert boundary.json()["binary_threshold"] == 0.15
    assert medium.json()["risk_level"] == "MEDIUM"
    assert medium.json()["probability"] == pytest.approx(0.4)
    assert high.json()["predicted_class"] == 1
    assert high.json()["risk_level"] == "HIGH"
    assert "collision" in high.json()["not_estimated"]
    direct = predict_one(session, _features(longitude=0.7))
    explained = explain_frame(
        session.estimator,
        _frame(longitude=0.7),
        binary_threshold=session.threshold,
        bands=session.bands,
    )[0]
    assert direct["probability"] == pytest.approx(explained["probability"])
    assert direct["predicted_class"] == explained["predicted_class"]
    assert direct["risk_level"] == explained["category"]


def test_invalid_requests_are_rejected(tmp_path: Path) -> None:
    client = TestClient(create_app(_session(tmp_path), database_url=_database_url(tmp_path)))
    missing = dict(_features())
    del missing["longitude"]
    assert client.post("/predictions", json=missing).status_code == 422
    extra = _features()
    extra["collision_severity"] = "1"
    leaked = client.post("/predictions", json=extra)
    assert leaked.status_code == 422
    unknown = _features()
    unknown["favourite_colour"] = "navy"
    assert client.post("/predictions", json=unknown).status_code == 422
    bad_number = _features()
    bad_number["longitude"] = "east"
    assert client.post("/predictions", json=bad_number).status_code == 422
    assert client.post("/predictions", json=[]).status_code == 422
    malformed = client.post(
        "/predictions",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 422
    with pytest.raises(InferenceInputError):
        predict_one(_session(tmp_path), _features(longitude=True))


def test_missing_and_corrupt_artifacts_do_not_invent_a_score(tmp_path: Path) -> None:
    idle = TestClient(create_app(load=False, database_url=_database_url(tmp_path)))
    assert idle.get("/health").json()["ready"] is False
    assert idle.get("/model").status_code == 503
    assert idle.post("/predictions", json=_features()).status_code == 503
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ArtifactUnavailable):
        open_session(empty, empty / "risk-bands.json")
    phase6, bands = _write_fixture(tmp_path / "broken")
    bands.write_text("{", encoding="utf-8")
    with pytest.raises(ArtifactUnavailable):
        open_session(phase6, bands)
    mismatched = _write_fixture(tmp_path / "threshold")
    payload = json.loads(mismatched[1].read_text(encoding="utf-8"))
    payload["binary_threshold"] = 0.5
    mismatched[1].write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ArtifactUnavailable, match="threshold"):
        open_session(mismatched[0], mismatched[1])


def test_real_frozen_artifact_is_served_without_being_rewritten(tmp_path: Path) -> None:
    phase6 = Path("data/models/phase6-v1")
    bands = Path("data/models/phase7-v1/risk-bands.json")
    if not (phase6 / "selected-pipeline.joblib").is_file() or not bands.is_file():
        pytest.skip("frozen Phase 6 and Phase 7 artifacts are not in this checkout")
    before = {path: Path(path).read_bytes() for path in PROTECTED}
    session = open_session(phase6, bands)
    assert session.artifact_role == "frozen_phase6"
    assert session.threshold == 0.15
    assert session.bands["low_below"] == pytest.approx(0.196970155937929)
    assert session.bands["high_at_or_above"] == pytest.approx(0.3126165522731136)
    client = TestClient(create_app(session, database_url=_database_url(tmp_path)))
    identity = client.get("/model")
    assert identity.status_code == 200
    assert identity.json()["binary_threshold"] == 0.15
    assert identity.json()["artifact_role"] == "frozen_phase6"
    scored = client.post("/predictions", json=_features(longitude=-0.1, latitude=51.5))
    assert scored.status_code == 200
    assert 0.0 <= scored.json()["probability"] <= 1.0
    assert scored.json()["binary_threshold"] == 0.15
    assert scored.json()["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    for path, content in before.items():
        assert Path(path).read_bytes() == content


def _database_url(tmp_path: Path) -> str:
    return "sqlite:///" + (tmp_path / "api-history.sqlite3").resolve().as_posix()


def _session(directory: Path):
    phase6, bands = _write_fixture(directory / "fixture")
    return open_session(phase6, bands)


def _write_fixture(directory: Path, *, threshold: float = 0.15) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "fixture.joblib"
    joblib.dump(LongitudeFixture(), artifact)
    artifact_sha = file_sha256(artifact)
    decision = dict.fromkeys(DECISION_KEYS)
    decision.update(
        {
            "phase": 6,
            "question": (
                "Given a reported personal-injury collision, "
                "was it fatal or serious rather than slight?"
            ),
            "not_estimated": "Whether a collision occurs.",
            "model": "fixture_not_phase6",
            "calibration_method": "none",
            "calibration_fitted_on": "synthetic rows inside the test",
            "calibration_cv_splits": 0,
            "calibration_ensemble": False,
            "calibration_cv_shuffle": False,
            "random_seed": 0,
            "threshold": threshold,
            "threshold_reference": 0.5,
            "threshold_objective": "fixture",
            "threshold_f1_margin": 0.01,
            "feature_spec_version": 1,
            "source_sha256": "fixture",
            "positive_codes": ["1", "2"],
            "negative_codes": ["3"],
            "positive_label": 1,
            "negative_label": 0,
            "training_period": [],
            "validation_period": ["2024"],
            "test_period": ["2025"],
            "test_used_for_selection": False,
            "reference_artifact": "not-a-phase5-artifact",
            "reference_artifact_sha256": "fixture",
            "selected_artifact": artifact.name,
            "selected_artifact_sha256": artifact_sha,
            "calibration_comparison_sha256": "fixture",
            "threshold_comparison_sha256": "fixture",
            "selection_rule_calibration": "fixture",
            "selection_rule_threshold": "fixture",
            "chosen_because": "synthetic API fixture, not the Phase 6 model",
            "validation_metrics_are_selection_results": False,
        }
    )
    digest = decision_hash(decision)
    frozen = {
        "artifact_role": FIXTURE_ROLE,
        "decision": decision,
        "decision_sha256": digest,
    }
    (directory / "frozen-config.json").write_text(
        json.dumps(frozen, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    bands_path = directory / "risk-bands.json"
    bands = {
        "binary_threshold": threshold,
        "decision_sha256": digest,
        "high_at_or_above": 0.7,
        "low_below": 0.4,
        "method": "synthetic fixture boundaries for the API test",
        "selected_artifact_sha256": artifact_sha,
        "test_period_used": False,
    }
    bands_path.write_text(json.dumps(bands, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return directory, bands_path


def _features(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {name: "1" for name in APPROVED_NAMES}
    for name in NUMERIC_FEATURES:
        row[name] = 1.0
    row["longitude"] = 0.2
    row.update(overrides)
    return row


def _frame(**overrides: object):
    import pandas as pd

    return pd.DataFrame([_features(**overrides)])
