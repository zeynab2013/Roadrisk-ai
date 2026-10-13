"""Correlation IDs and log redaction. The scored model is a synthetic fixture."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from apps.api.correlation import CORRELATION_HEADER, accept_correlation_id
from apps.api.main import create_app
from fastapi.testclient import TestClient
from tests.integration.test_api import _database_url, _features, _session


def test_invalid_correlation_ids_are_replaced() -> None:
    generated = accept_correlation_id(None)
    assert generated.isalnum()
    assert "\n" not in generated
    assert accept_correlation_id("trace-1") == "trace-1"
    injected = accept_correlation_id("trace\nlevel=ERROR secret")
    assert "\n" not in injected
    assert injected != "trace\nlevel=ERROR secret"
    assert accept_correlation_id("x" * 65) != "x" * 65


def test_response_returns_a_valid_correlation_id_and_logs_omit_the_body(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app(_session(tmp_path), database_url=_database_url(tmp_path)))
    body = _features(longitude=-0.12, latitude=51.5)
    body["collision_severity"] = "1"
    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/predictions",
            json=body,
            headers={CORRELATION_HEADER: "browser-check-1"},
        )
    assert response.status_code == 422
    assert response.headers[CORRELATION_HEADER] == "browser-check-1"
    assert "browser-check-1" in caplog.text
    assert "path=/predictions" in caplog.text
    assert "status=422" in caplog.text
    assert "collision_severity" not in caplog.text
    assert "-0.12" not in caplog.text
    assert "sqlite" not in caplog.text.lower()
    assert str(tmp_path) not in caplog.text


def test_a_newline_in_the_incoming_id_is_not_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app(_session(tmp_path), database_url=_database_url(tmp_path)))
    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/predictions",
            json=[],
            headers={CORRELATION_HEADER: "ok\nINJECTED"},
        )
    returned = response.headers[CORRELATION_HEADER]
    assert response.status_code == 422
    assert "\n" not in returned
    assert "INJECTED" not in caplog.text
    assert f"correlation_id={returned}" in caplog.text


def test_missing_artifacts_do_not_return_a_filesystem_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "absent-phase6"
    secret_db = tmp_path / "secret-history.sqlite3"
    monkeypatch.setenv("ROADRISK_PHASE6_DIR", str(missing))
    monkeypatch.setenv("ROADRISK_BANDS_PATH", str(tmp_path / "absent-bands.json"))
    monkeypatch.setenv("ROADRISK_DATABASE_URL", f"sqlite:///{secret_db.as_posix()}")
    client = TestClient(create_app())
    response = client.get("/model")
    assert response.status_code == 503
    assert response.json()["detail"] == "Model artifacts are not loaded"
    assert str(missing) not in response.text
    assert "secret-history.sqlite3" not in response.text
    assert "sqlite" not in response.text.lower()
    health = client.get("/health")
    assert health.json()["ready"] is False
    assert health.headers[CORRELATION_HEADER]
