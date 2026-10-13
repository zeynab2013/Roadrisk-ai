"""Derive Phase 7 research bands from the 2024 validation scores.

Example:
    python -m roadrisk.inference bands --manifest configs/data_manifest.json

The command scores the 2024 validation split with the frozen pipeline.
It does not score 2025 and does not rewrite Phase 6 files.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from roadrisk.config import load_settings
from roadrisk.data.errors import DataError
from roadrisk.features.spec import SPEC_VERSION
from roadrisk.inference.artifacts import PHASE7_DIR_NAME, RISK_BANDS_FILE, load_frozen_model
from roadrisk.inference.explain import explain_frame, global_permutation_summary
from roadrisk.inference.groups import summarize_groups
from roadrisk.inference.risk import BAND_METHOD, boundaries_from_validation, load_risk_bands
from roadrisk.logging import configure_logging
from roadrisk.training.phase6 import PHASE6_DIR_NAME, file_sha256
from roadrisk.training.population import training_and_validation
from roadrisk.training.run import (
    assert_feature_provenance,
    load_feature_table,
    utc_now,
    verify_collision_file,
)
from roadrisk.training.scoring import positive_scores

logger = logging.getLogger(__name__)
POPULATION = (
    "2024 validation rows. Each row is a reported personal-injury collision. "
    "The summary is not an exposure-adjusted collision rate."
)


def main(argv: list[str] | None = None) -> int:
    """Run a Phase 7 command. Returns a process status code."""

    parser = argparse.ArgumentParser(prog="python -m roadrisk.inference")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bands = subparsers.add_parser(
        "bands",
        help="Derive 2024 probability bands and a global importance sample",
    )
    bands.add_argument("--manifest", type=Path, default=Path("configs/data_manifest.json"))
    bands.add_argument("--root", type=Path, default=Path.cwd())
    bands.add_argument(
        "--features",
        type=Path,
        default=Path("data/processed/collision-features-v1.csv"),
    )
    bands.add_argument("--phase6-dir", type=Path, default=None)
    bands.add_argument("--output-dir", type=Path, default=None)
    bands.add_argument("--minimum-support", type=int, default=50)
    explain = subparsers.add_parser(
        "explain",
        help="Explain feature rows with the frozen pipeline",
    )
    explain.add_argument("--rows", type=Path, required=True)
    explain.add_argument("--root", type=Path, default=Path.cwd())
    explain.add_argument("--phase6-dir", type=Path, default=None)
    explain.add_argument("--bands", type=Path, default=None)
    explain.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    settings = load_settings(project_root=args.root)
    configure_logging(settings.log_level)
    try:
        if args.command == "bands":
            _bands(args, settings.data_dir)
        elif args.command == "explain":
            _explain(args, settings.data_dir)
        return 0
    except DataError as exc:
        logger.error("%s", exc)
        return 1


def _bands(args, data_dir: Path) -> None:
    root = args.root
    features = _resolve(root, args.features)
    phase6_dir = args.phase6_dir or (settings_models(data_dir) / PHASE6_DIR_NAME)
    phase6_dir = phase6_dir if phase6_dir.is_absolute() else _resolve(root, phase6_dir)
    output_dir = args.output_dir or (settings_models(data_dir) / PHASE7_DIR_NAME)
    output_dir = output_dir if output_dir.is_absolute() else _resolve(root, output_dir)
    if output_dir.name in {PHASE6_DIR_NAME, "baselines-v1"}:
        raise DataError("Phase 7 must not write into a Phase 5 or Phase 6 directory")
    estimator, decision = load_frozen_model(phase6_dir)
    sha256, _byte_size = verify_collision_file(data_dir, _resolve(root, args.manifest))
    meta_path = features.with_name("collision-features-v1.meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert_feature_provenance(meta, sha256=sha256)
    frame = load_feature_table(features)
    _training, validation, _unused_test_rows = training_and_validation(frame)
    del _training, _unused_test_rows, frame
    logger.info("Scoring %s validation rows for research bands", len(validation))
    chosen = boundaries_from_validation(estimator, validation)
    frozen_path = phase6_dir / "frozen-config.json"
    frozen_record = json.loads(frozen_path.read_text(encoding="utf-8"))
    payload = {
        "phase": 7,
        "question": decision["question"],
        "not_estimated": decision["not_estimated"],
        "model": decision["model"],
        "calibration_method": decision["calibration_method"],
        "binary_threshold": decision["threshold"],
        "binary_threshold_role": (
            "Phase 6 classification threshold. A probability at or above it is "
            "the fatal-or-serious class. It is not a category boundary."
        ),
        "low_below": chosen["low_below"],
        "high_at_or_above": chosen["high_at_or_above"],
        "inclusivity": (
            "LOW if probability < low_below; "
            "MEDIUM if low_below <= probability < high_at_or_above; "
            "HIGH if probability >= high_at_or_above."
        ),
        "method": BAND_METHOD,
        "lower_quantile": chosen["lower_quantile"],
        "upper_quantile": chosen["upper_quantile"],
        "validation_period": ["2024"],
        "validation_rows": chosen["rows"],
        "validation_score_mean": chosen["score_mean"],
        "test_period_used": False,
        "feature_spec_version": SPEC_VERSION,
        "source_sha256": sha256,
        "decision_sha256": frozen_record["decision_sha256"],
        "frozen_config_sha256": file_sha256(frozen_path),
        "selected_artifact_sha256": decision["selected_artifact_sha256"],
        "created_at": utc_now(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / RISK_BANDS_FILE, payload)
    scores = positive_scores(estimator, validation)
    summary = summarize_groups(
        validation,
        scores,
        payload,
        minimum_support=args.minimum_support,
        population=POPULATION,
    )
    _write(output_dir / "group-summary.json", summary)
    logger.info("Estimating global permutation importance on a 2024 sample")
    importance = global_permutation_summary(estimator, validation)
    importance["test_period_used"] = False
    _write(output_dir / "global-importance.json", importance)
    report_dir = root / "reports" / "phase7"
    report_dir.mkdir(parents=True, exist_ok=True)
    for name in (RISK_BANDS_FILE, "group-summary.json", "global-importance.json"):
        text = (output_dir / name).read_text(encoding="utf-8")
        (report_dir / name).write_text(text, encoding="utf-8")
    logger.info(
        "Bands: LOW below %s, HIGH at or above %s",
        payload["low_below"],
        payload["high_at_or_above"],
    )
    logger.info("Artifacts: %s", output_dir)


def _explain(args, data_dir: Path) -> None:
    """Explain a caller-supplied feature file. 2025 rows are refused."""

    root = args.root
    output = _resolve(root, args.output)
    if PHASE6_DIR_NAME in output.parts or "baselines-v1" in output.parts:
        raise DataError("Explanations must not be written into a Phase 5 or Phase 6 directory")
    phase6_dir = args.phase6_dir or (settings_models(data_dir) / PHASE6_DIR_NAME)
    phase6_dir = phase6_dir if phase6_dir.is_absolute() else _resolve(root, phase6_dir)
    rows_path = _resolve(root, args.rows)
    if not rows_path.is_file():
        raise DataError(f"Explanation rows are missing: {rows_path}")
    estimator, decision = load_frozen_model(phase6_dir)
    frame = pd.read_csv(rows_path, dtype=str, keep_default_na=False)
    bands = None
    if args.bands is not None:
        frozen = json.loads((phase6_dir / "frozen-config.json").read_text(encoding="utf-8"))
        bands = load_risk_bands(
            _resolve(root, args.bands),
            expected_decision_sha256=str(frozen["decision_sha256"]),
            expected_artifact_sha256=str(decision["selected_artifact_sha256"]),
        )
    result = explain_frame(
        estimator,
        frame,
        binary_threshold=float(decision["threshold"]),
        bands=bands,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write(output, result)
    logger.info("Wrote %s explanations to %s", len(result), output)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve(root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (root / path).resolve()


def settings_models(data_dir: Path) -> Path:
    return data_dir / "models"


if __name__ == "__main__":
    raise SystemExit(main())
