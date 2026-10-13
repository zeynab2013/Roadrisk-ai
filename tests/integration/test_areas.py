"""The area route reads a saved summary. It does not score collisions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from apps.api.main import create_app
from fastapi.testclient import TestClient
from tests.integration.test_api import _database_url, _session


def test_area_route_does_not_score() -> None:
    text = Path("apps/api/routes/areas.py").read_text(encoding="utf-8")
    assert "positive_scores" not in text
    assert "held_out_rows" not in text
    assert "predict_one" not in text


def test_area_summary_must_match_the_loaded_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path)
    directory = tmp_path / "phase7"
    directory.mkdir()
    _write_pair(directory, session.decision_sha256)
    monkeypatch.setenv("ROADRISK_BANDS_PATH", str(directory / "risk-bands.json"))
    client = TestClient(create_app(session, database_url=_database_url(tmp_path)))
    response = client.get("/area-summaries")
    assert response.status_code == 200
    body = response.json()
    assert body["grouping_field"] == "urban_or_rural_area"
    assert body["rows"] == 3
    assert body["groups"][0]["label"] == "Urban"
    assert "unsafe" in body["not_estimated"]
    assert "safety ranking" in body["limitation"]


def test_area_summary_rejects_a_different_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path)
    directory = tmp_path / "other"
    directory.mkdir()
    _write_pair(directory, "not-the-loaded-decision")
    monkeypatch.setenv("ROADRISK_BANDS_PATH", str(directory / "risk-bands.json"))
    client = TestClient(create_app(session, database_url=_database_url(tmp_path)))
    response = client.get("/area-summaries")
    assert response.status_code == 409
    assert response.json()["detail"] == "Area summary is not tied to the loaded model"


def test_missing_area_summary_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path)
    missing = tmp_path / "absent" / "risk-bands.json"
    monkeypatch.setenv("ROADRISK_BANDS_PATH", str(missing))
    client = TestClient(create_app(session, database_url=_database_url(tmp_path)))
    response = client.get("/area-summaries")
    assert response.status_code == 503
    assert response.json()["detail"] == "Area summary is not available"


def _write_pair(directory: Path, decision_sha256: str) -> None:
    bands = {
        "binary_threshold": 0.15,
        "decision_sha256": decision_sha256,
        "high_at_or_above": 0.7,
        "low_below": 0.4,
        "method": "fixture",
        "test_period_used": False,
    }
    summary = {
        "grouping_field": "urban_or_rural_area",
        "grouping_reason": "urban_or_rural_area is an approved feature.",
        "groups": [
            {
                "area_id": "1",
                "category_counts": {"HIGH": 0, "LOW": 1, "MEDIUM": 0},
                "category_shares": {"HIGH": 0.0, "LOW": 1.0, "MEDIUM": 0.0},
                "collisions": 1,
                "label": "Urban",
                "mean_predicted_probability": 0.2,
            }
        ],
        "limitation": "Counts are recorded collisions. They are not a safety ranking.",
        "minimum_support": 50,
        "missing_location_rows": 1,
        "not_estimated": "Whether a collision occurs, or whether an area is unsafe.",
        "population": "synthetic rows",
        "rows": 3,
        "supported_groups": [],
        "unsupported_location_rows": 0,
    }
    (directory / "risk-bands.json").write_text(json.dumps(bands), encoding="utf-8")
    (directory / "group-summary.json").write_text(json.dumps(summary), encoding="utf-8")
