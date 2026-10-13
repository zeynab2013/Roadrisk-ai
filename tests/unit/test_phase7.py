"""Phase 7 explanations, research bands, and urban/rural summaries.

Fixtures are synthetic. The real 2025 evaluation file is only hashed, not scored.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

import numpy as np
import pandas as pd

from roadrisk.data.errors import DataError, FeatureContractError
from roadrisk.features.spec import APPROVED_NAMES
from roadrisk.inference.artifacts import load_frozen_model
from roadrisk.inference.explain import explain_frame, global_permutation_summary
from roadrisk.inference.groups import summarize_groups
from roadrisk.inference.risk import (
    assign_category,
    boundaries_from_validation,
    choose_category_boundaries,
    load_risk_bands,
    validate_boundaries,
)
from roadrisk.training.columns import LABEL_COLUMN
from roadrisk.training.phase6 import file_sha256
from roadrisk.training.scoring import positive_scores

PROTECTED = (
    "data/models/phase6-v1/frozen-config.json",
    "data/models/phase6-v1/selected-pipeline.joblib",
    "data/models/phase6-v1/calibration-comparison.json",
    "data/models/phase6-v1/threshold-comparison.json",
    "data/models/phase6-v1/test-evaluation.json",
    "data/models/baselines-v1/comparison.json",
    "data/models/baselines-v1/comparison.md",
    "data/models/baselines-v1/dummy.joblib",
    "data/models/baselines-v1/hist_gradient_boosting.joblib",
    "data/models/baselines-v1/logistic_regression.joblib",
    "data/models/baselines-v1/random_forest.joblib",
)


class _LongitudeScore:
    """Tiny stand-in. The positive probability is the longitude, or 0.4 if missing."""

    classes_ = np.array([0, 1])

    def predict_proba(self, frame):
        raw = pd.to_numeric(frame["longitude"], errors="coerce").to_numpy(dtype=float)
        positive = np.where(np.isnan(raw), 0.4, np.clip(raw, 0.0, 1.0))
        return np.column_stack([1.0 - positive, positive])


def test_category_quantiles_are_ordered_and_repeatable() -> None:
    scores = np.linspace(0.2, 0.8, 11)
    first = choose_category_boundaries(scores)
    second = choose_category_boundaries(scores)
    assert first == second
    assert first["low_below"] == pytest.approx(0.5)
    assert first["high_at_or_above"] > first["low_below"]
    assert first["low_below"] not in {0.33, 0.66}
    assert "2025" in str(first["method"])
    with pytest.raises(DataError):
        choose_category_boundaries([])
    with pytest.raises(DataError):
        validate_boundaries(0.8, 0.2)


def test_saved_band_boundaries_keep_class_and_band_separate() -> None:
    """These cuts are the published Phase 7 values. This test does not recompute them."""

    low_below = 0.196970155937929
    high_at_or_above = 0.3126165522731136
    bands = {"low_below": low_below, "high_at_or_above": high_at_or_above}
    assert assign_category(np.nextafter(low_below, 0.0), bands) == "LOW"
    assert assign_category(low_below, bands) == "MEDIUM"
    assert assign_category(0.15, bands) == "LOW"
    assert assign_category(np.nextafter(high_at_or_above, 0.0), bands) == "MEDIUM"
    assert assign_category(high_at_or_above, bands) == "HIGH"


def test_risk_band_file_rejects_an_incomplete_object(tmp_path: Path) -> None:
    path = tmp_path / "risk-bands.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(DataError, match="JSON object"):
        load_risk_bands(path)
    path.write_text(json.dumps({"low_below": 0.2, "high_at_or_above": 0.7}), encoding="utf-8")
    with pytest.raises(DataError, match="missing"):
        load_risk_bands(path)


def test_category_edges_and_invalid_probabilities() -> None:
    bands = {"low_below": 0.2, "high_at_or_above": 0.8}
    assert assign_category(0.0, bands) == "LOW"
    assert assign_category(0.199999, bands) == "LOW"
    assert assign_category(0.2, bands) == "MEDIUM"
    assert assign_category(0.799999, bands) == "MEDIUM"
    assert assign_category(0.8, bands) == "HIGH"
    assert assign_category(1.0, bands) == "HIGH"
    shifted = {"low_below": 0.6, "high_at_or_above": 0.9}
    assert assign_category(0.5, bands) == "MEDIUM"
    assert assign_category(0.5, shifted) == "LOW"
    with pytest.raises(DataError):
        assign_category(1.1, bands)
    with pytest.raises(DataError):
        assign_category(float("nan"), bands)


def test_category_selection_rejects_2025_before_scoring(monkeypatch: pytest.MonkeyPatch) -> None:
    def opened(*_args, **_kwargs):
        raise AssertionError("2025 frame was scored")

    monkeypatch.setattr("roadrisk.inference.risk.positive_scores", opened)
    frame = _rows([("2025", "test", 0.2)])
    with pytest.raises(FeatureContractError, match="2024"):
        boundaries_from_validation(object(), frame)
    mixed = _rows([("2024", "validation", 0.2), ("2023", "validation", 0.3)])
    with pytest.raises(FeatureContractError, match="2024"):
        boundaries_from_validation(object(), mixed)
    with pytest.raises(FeatureContractError, match="empty"):
        boundaries_from_validation(object(), _rows([]))


def test_binary_threshold_stays_at_0_15_and_explanation_is_local() -> None:
    low = explain_frame(
        _LongitudeScore(), _rows([("2024", "validation", 0.149)]), binary_threshold=0.15
    )
    high = explain_frame(
        _LongitudeScore(), _rows([("2024", "validation", 0.15)]), binary_threshold=0.15
    )
    assert low[0]["predicted_class"] == 0
    assert high[0]["predicted_class"] == 1
    assert high[0]["binary_threshold"] == 0.15
    assert high[0]["not_estimated"] == "Whether a collision occurs."
    features = [row["feature"] for row in high[0]["local_sensitivity"]]
    assert features == list(APPROVED_NAMES)
    assert "collision_severity" not in features
    assert "severity_serious_or_fatal" not in features
    longitude = next(row for row in high[0]["local_sensitivity"] if row["feature"] == "longitude")
    assert longitude["observed_value"] == pytest.approx(0.15)
    assert longitude["probability_change"] == pytest.approx(0.15 - 0.4)
    weather = next(
        row for row in high[0]["local_sensitivity"] if row["feature"] == "weather_conditions"
    )
    assert weather["probability_change"] == pytest.approx(0.0)
    assert "does not show that the field caused" in high[0]["limitation"]
    bands = {"low_below": 0.1, "high_at_or_above": 0.5}
    banded = explain_frame(
        _LongitudeScore(),
        _rows([("2024", "validation", 0.15)]),
        binary_threshold=0.15,
        bands=bands,
    )
    assert banded[0]["category"] == "MEDIUM"
    with pytest.raises(FeatureContractError):
        explain_frame(_LongitudeScore(), pd.DataFrame([{"longitude": 0.2}]), binary_threshold=0.15)
    held_out = _rows([("2025", "test", 0.2)])
    with pytest.raises(FeatureContractError, match="2025"):
        explain_frame(_LongitudeScore(), held_out, binary_threshold=0.15)


def test_risk_band_file_rejects_a_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "risk-bands.json"
    with pytest.raises(DataError, match="missing"):
        load_risk_bands(path)
    payload = {
        "low_below": 0.7,
        "high_at_or_above": 0.2,
        "method": "quantiles",
        "binary_threshold": 0.15,
        "test_period_used": False,
        "decision_sha256": "abc",
        "selected_artifact_sha256": "def",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DataError, match="boundaries"):
        load_risk_bands(path)
    payload["low_below"] = 0.2
    payload["high_at_or_above"] = 0.7
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DataError, match="frozen decision"):
        load_risk_bands(path, expected_decision_sha256="other")
    loaded = load_risk_bands(path, expected_decision_sha256="abc", expected_artifact_sha256="def")
    assert loaded["binary_threshold"] == 0.15
    payload["test_period_used"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FeatureContractError, match="2025"):
        load_risk_bands(path)


def test_group_summary_counts_and_support() -> None:
    bands = {"low_below": 0.3, "high_at_or_above": 0.7}
    frame = pd.DataFrame(
        {
            GROUP: ["1", "1", "1", "2", "", "9"],
            LABEL_COLUMN: [1, 0, 1, 0, 1, 0],
        }
    )
    probabilities = [0.1, 0.4, 0.9, 0.95, 0.2, 0.2]
    summary = summarize_groups(
        frame,
        probabilities,
        bands,
        minimum_support=2,
        population="synthetic validation rows",
    )
    flipped = frame.copy()
    flipped[LABEL_COLUMN] = 1 - flipped[LABEL_COLUMN]
    other = summarize_groups(
        flipped,
        probabilities,
        bands,
        minimum_support=2,
        population="synthetic validation rows",
    )
    assert summary["groups"] == other["groups"]
    assert summary["missing_location_rows"] == 1
    assert summary["unsupported_location_rows"] == 1
    urban = next(row for row in summary["groups"] if row["area_id"] == "1")
    assert urban["collisions"] == 3
    assert urban["label"] == "Urban"
    assert urban["category_counts"] == {"LOW": 1, "MEDIUM": 1, "HIGH": 1}
    assert urban["category_shares"]["HIGH"] == pytest.approx(1 / 3)
    assert urban["mean_predicted_probability"] == pytest.approx((0.1 + 0.4 + 0.9) / 3)
    assert [row["area_id"] for row in summary["supported_groups"]] == ["1"]
    assert "unsafe" in summary["not_estimated"]
    assert "not a safety ranking" in summary["limitation"]
    empty = next(row for row in summary["groups"] if row["area_id"] == "3")
    assert empty["collisions"] == 0
    assert empty["category_shares"]["HIGH"] is None
    assert empty["mean_predicted_probability"] is None
    with pytest.raises(DataError, match="row count"):
        summarize_groups(
            frame, probabilities[:-1], bands, minimum_support=2, population="synthetic"
        )
    with pytest.raises(DataError, match="at least 1"):
        summarize_groups(
            frame, probabilities, bands, minimum_support=0, population="synthetic"
        )


def test_global_importance_rejects_a_non_validation_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    def opened(*_args, **_kwargs):
        raise AssertionError("permutation importance ran")

    monkeypatch.setattr("sklearn.inspection.permutation_importance", opened)
    frame = _rows([("2025", "test", 0.4)])
    with pytest.raises(FeatureContractError, match="2024"):
        global_permutation_summary(_LongitudeScore(), frame)


def test_saved_phase7_artifacts_cite_2024_and_the_frozen_decision() -> None:
    bands_path = Path("data/models/phase7-v1/risk-bands.json")
    groups_path = Path("data/models/phase7-v1/group-summary.json")
    importance_path = Path("data/models/phase7-v1/global-importance.json")
    if not bands_path.is_file():
        pytest.skip("Phase 7 band artifact is not in this checkout")
    bands = load_risk_bands(
        bands_path,
        expected_decision_sha256="9461dce554913b7617c1632d5bd8a23ab3e4185542c3f5e65baab5fac14ef09b",
        expected_artifact_sha256="43143b15178c5dc2dbe5c79ed6e12e1217d5ba6cefab737f5f7ac24f508bb478",
    )
    assert bands["binary_threshold"] == 0.15
    assert bands["validation_period"] == ["2024"]
    assert bands["validation_rows"] == 100927
    assert bands["test_period_used"] is False
    assert bands["lower_quantile"] == 0.5
    assert bands["upper_quantile"] == 0.9
    assert bands["low_below"] == pytest.approx(0.196970155937929)
    assert bands["high_at_or_above"] == pytest.approx(0.3126165522731136)
    assert bands["low_below"] not in {0.33, 0.66}
    report = Path("reports/phase7/risk-bands.json")
    if report.is_file():
        assert report.read_bytes() == bands_path.read_bytes()
    if not groups_path.is_file() or not importance_path.is_file():
        pytest.skip("Phase 7 summary artifacts are not in this checkout")
    groups = json.loads(groups_path.read_text(encoding="utf-8"))
    assert groups["rows"] == 100927
    assert groups["grouping_field"] == "urban_or_rural_area"
    assert sum(row["collisions"] for row in groups["groups"]) == 100927
    assert [row["area_id"] for row in groups["supported_groups"]] == ["2", "1"]
    importance = json.loads(importance_path.read_text(encoding="utf-8"))
    assert importance["period"] == "2024"
    assert importance["test_period_used"] is False
    assert importance["not_a_local_explanation"] is True
    assert {row["feature"] for row in importance["features"]} == set(APPROVED_NAMES)


def test_phase7_sources_do_not_call_the_held_out_loader() -> None:
    sources = Path("src/roadrisk/inference").glob("*.py")
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert "held_out_rows" not in text
    assert "test-evaluation.json" not in text


def test_bands_command_refuses_a_phase6_output_directory() -> None:
    from roadrisk.inference.__main__ import main

    before = Path("data/models/phase6-v1/frozen-config.json").read_bytes()
    code = main(
        [
            "bands",
            "--output-dir",
            "data/models/phase6-v1",
            "--root",
            str(Path.cwd()),
        ]
    )
    assert code == 1
    assert Path("data/models/phase6-v1/frozen-config.json").read_bytes() == before


def test_protected_artifacts_survive_a_read_only_frozen_load() -> None:
    phase6 = Path("data/models/phase6-v1")
    pipeline = phase6 / "selected-pipeline.joblib"
    evaluation = phase6 / "test-evaluation.json"
    if not pipeline.is_file() or not evaluation.is_file():
        pytest.skip("frozen Phase 6 artifacts are not in this checkout")
    before = {path: Path(path).read_bytes() for path in PROTECTED}
    estimator, decision = load_frozen_model(phase6)
    assert decision["threshold"] == 0.15
    assert decision["calibration_method"] == "sigmoid"
    assert decision["model"] == "hist_gradient_boosting"
    explained = explain_frame(
        estimator, _rows([("2024", "validation", 0.2)]), binary_threshold=0.15
    )
    assert 0.0 <= explained[0]["probability"] <= 1.0
    assert file_sha256(pipeline) == decision["selected_artifact_sha256"]
    for path, content in before.items():
        assert Path(path).read_bytes() == content
    # The import keeps the scorer available for a direct call without scoring 2025.
    assert positive_scores is not None


def _rows(specs: list[tuple[str, str, float]]) -> pd.DataFrame:
    records = []
    for year, split, longitude in specs:
        row = {name: "1" for name in APPROVED_NAMES}
        row.update(
            {
                "collision_year": year,
                "split": split,
                "longitude": longitude,
                "latitude": 51.5,
                "hour": 8,
                "month": 1,
                LABEL_COLUMN: 0,
            }
        )
        records.append(row)
    if not records:
        return pd.DataFrame(columns=["collision_year", "split", *APPROVED_NAMES])
    return pd.DataFrame.from_records(records)


GROUP = "urban_or_rural_area"
