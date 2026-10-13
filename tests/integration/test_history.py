"""Prediction history uses a temporary SQLite file and the Phase 8 fixture model."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

import numpy as np
from apps.api.main import create_app
from apps.api.schemas import PredictionResponse
from apps.api.store import repository_for
from fastapi.testclient import TestClient
from tests.integration.fixture_estimator import LongitudeFixture
from tests.integration.test_api import _database_url, _features, _session

from roadrisk.inference.service import InferenceSession
from roadrisk.persistence.repository import PersistenceError


class _FailingScore(LongitudeFixture):
    """Returns a probability the service must reject."""

    def predict_proba(self, frame):
        count = len(frame)
        positive = np.full(count, 1.5)
        return np.column_stack([1.0 - positive, positive])


class _UnavailableHistory:
    def add(self, prediction, *, created_at=None):
        raise PersistenceError("storage failed")

    def list_records(self):
        raise PersistenceError("storage failed")


def test_inference_service_does_not_import_persistence() -> None:
    source = Path("src/roadrisk/inference/service.py").read_text(encoding="utf-8")
    assert "persistence" not in source
    assert "sqlalchemy" not in source
    script = (
        "import roadrisk.inference.service, sys; "
        "names = list(sys.modules); "
        "bad = [name for name in names if name.startswith('roadrisk.persistence') "
        "or name.startswith('sqlalchemy')]; "
        "raise SystemExit(1 if bad else 0)"
    )
    completed = subprocess.run([sys.executable, "-c", script], check=False)
    assert completed.returncode == 0


def test_importing_the_api_does_not_create_the_default_database(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("ROADRISK_DATABASE_URL", None)
    env["PYTHONPATH"] = str(Path.cwd())
    completed = subprocess.run(
        [sys.executable, "-c", "import apps.api.main"],
        check=False,
        cwd=tmp_path,
        env=env,
    )
    assert completed.returncode == 0
    assert list(tmp_path.rglob("*.sqlite3")) == []


def test_accepted_prediction_is_stored_and_listed(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post("/predictions", json=_features(longitude=0.7))
    assert created.status_code == 200
    body = created.json()
    assert set(body) == set(PredictionResponse.model_fields)
    assert body["predicted_class"] == 1
    assert body["risk_level"] == "HIGH"
    assert body["binary_threshold"] == 0.15
    assert "id" not in body
    listed = client.get("/predictions")
    assert listed.status_code == 200
    rows = listed.json()["predictions"]
    assert len(rows) == 1
    saved = rows[0]
    assert saved["id"] == 1
    assert saved["probability"] == pytest.approx(body["probability"])
    assert saved["predicted_class"] == body["predicted_class"]
    assert saved["risk_level"] == body["risk_level"]
    assert saved["model_version"] == body["model_version"]
    assert saved["created_at"].endswith(("+00:00", "Z"))


def test_predictions_are_listed_in_time_order_then_by_id(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.post("/predictions", json=_features(longitude=0.2)).status_code == 200
    assert client.post("/predictions", json=_features(longitude=0.8)).status_code == 200
    listed = client.get("/predictions")
    rows = listed.json()["predictions"]
    assert [row["id"] for row in rows] == [1, 2]
    assert rows[0]["created_at"] <= rows[1]["created_at"]
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    repository = repository_for(client.app)
    repository.add(rows[0], created_at=stamp)
    repository.add(rows[1], created_at=stamp)
    ordered = client.get("/predictions").json()["predictions"]
    tied = [row for row in ordered if row["created_at"].startswith("2026-01-01")]
    assert [row["id"] for row in tied] == [3, 4]
    keys = [(row["created_at"], row["id"]) for row in ordered]
    assert keys == sorted(keys)


def test_invalid_input_and_scoring_failure_are_not_stored(tmp_path: Path) -> None:
    client = _client(tmp_path)
    missing = dict(_features())
    del missing["hour"]
    rejected = client.post("/predictions", json=missing)
    assert rejected.status_code == 422
    assert client.get("/predictions").json()["predictions"] == []
    session = _session(tmp_path)
    broken = InferenceSession(
        estimator=_FailingScore(),
        decision=session.decision,
        bands=session.bands,
        decision_sha256=session.decision_sha256,
        artifact_role=session.artifact_role,
    )
    failing = TestClient(create_app(broken, database_url=_database_url(tmp_path / "failed")))
    scored = failing.post("/predictions", json=_features())
    assert scored.status_code == 500
    assert "probability" not in scored.json()
    assert failing.get("/predictions").json()["predictions"] == []


def test_database_errors_are_not_reported_as_success(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.app.state.history = _UnavailableHistory()
    failed = client.post("/predictions", json=_features(longitude=0.7))
    assert failed.status_code == 503
    assert failed.json()["detail"] == "The prediction could not be stored"
    assert "sqlite" not in failed.text.lower()
    assert str(tmp_path) not in failed.text
    unread = client.get("/predictions")
    assert unread.status_code == 503
    assert unread.json()["detail"] == "Prediction history is unavailable"
    assert "sqlite" not in unread.text.lower()


def _client(tmp_path: Path) -> TestClient:
    session = _session(tmp_path)
    return TestClient(create_app(session, database_url=_database_url(tmp_path)))
