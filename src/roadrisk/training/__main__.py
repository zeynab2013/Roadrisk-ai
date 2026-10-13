"""Train the four untuned baselines on the verified feature table.

Example:
    python -m roadrisk.training train --manifest configs/data_manifest.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from roadrisk.config import load_settings
from roadrisk.data.errors import DataError
from roadrisk.features.spec import SPEC_VERSION
from roadrisk.logging import configure_logging
from roadrisk.training.phase6 import (
    BASELINE_DIR_NAME,
    PHASE6_DIR_NAME,
    evaluate_frozen,
    refuse_existing_evaluation,
    select_from_frame,
)
from roadrisk.training.pipelines import SEED
from roadrisk.training.population import training_and_validation
from roadrisk.training.run import (
    MODEL_DIR_NAME,
    assert_feature_provenance,
    dependency_versions,
    fit_baselines,
    load_feature_table,
    save_run,
    utc_now,
    verify_collision_file,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run a training command. Returns a process status code."""

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--manifest",
        type=Path,
        default=Path("configs/data_manifest.json"),
        help="Path to the dataset manifest",
    )
    common.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root used to resolve relative paths",
    )
    parser = argparse.ArgumentParser(prog="python -m roadrisk.training")
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser(
        "train",
        parents=[common],
        help="Fit baselines on 2021-2023 and compare them on 2024",
    )
    train.add_argument(
        "--features",
        type=Path,
        default=Path("data/processed/collision-features-v1.csv"),
        help="Feature table built by python -m roadrisk.features build",
    )
    train.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Artifact directory. Default: data/models/baselines-v1",
    )
    select = subparsers.add_parser(
        "select",
        parents=[common],
        help="Calibrate and choose a threshold on 2024, then freeze the configuration",
    )
    select.add_argument(
        "--features",
        type=Path,
        default=Path("data/processed/collision-features-v1.csv"),
        help="Feature table built by python -m roadrisk.features build",
    )
    select.add_argument(
        "--baselines",
        type=Path,
        default=None,
        help="Phase 5 artifact directory. Default: data/models/baselines-v1",
    )
    select.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Phase 6 artifact directory. Default: data/models/phase6-v1",
    )
    select.add_argument(
        "--cv",
        type=int,
        default=3,
        help="Training-period folds for calibration. Default: 3",
    )
    evaluate = subparsers.add_parser(
        "evaluate",
        parents=[common],
        help="Score the frozen Phase 6 pipeline on 2025 once",
    )
    evaluate.add_argument(
        "--features",
        type=Path,
        default=Path("data/processed/collision-features-v1.csv"),
        help="Feature table built by python -m roadrisk.features build",
    )
    evaluate.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Phase 6 artifact directory. Default: data/models/phase6-v1",
    )
    args = parser.parse_args(argv)
    settings = load_settings(project_root=args.root)
    configure_logging(settings.log_level)
    try:
        if args.command == "train":
            features = args.features
            if not features.is_absolute():
                features = (args.root / features).resolve()
            output_dir = args.output_dir
            if output_dir is None:
                output_dir = settings.data_dir / "models" / MODEL_DIR_NAME
            elif not output_dir.is_absolute():
                output_dir = (args.root / output_dir).resolve()
            _train(settings.data_dir, args.manifest, features, output_dir, args.root)
        elif args.command == "select":
            features = _resolve(args.root, args.features)
            baselines = args.baselines
            if baselines is None:
                baselines = settings.data_dir / "models" / BASELINE_DIR_NAME
            else:
                baselines = _resolve(args.root, baselines)
            output_dir = args.output_dir
            if output_dir is None:
                output_dir = settings.data_dir / "models" / PHASE6_DIR_NAME
            else:
                output_dir = _resolve(args.root, output_dir)
            _select(
                settings.data_dir,
                args.manifest,
                features,
                baselines,
                output_dir,
                args.root,
                args.cv,
            )
        elif args.command == "evaluate":
            features = _resolve(args.root, args.features)
            output_dir = args.output_dir
            if output_dir is None:
                output_dir = settings.data_dir / "models" / PHASE6_DIR_NAME
            else:
                output_dir = _resolve(args.root, output_dir)
            _evaluate(settings.data_dir, args.manifest, features, output_dir, args.root)
        return 0
    except DataError as exc:
        logger.error("%s", exc)
        return 1


def _train(
    data_dir: Path,
    manifest_path: Path,
    features: Path,
    output_dir: Path,
    root: Path,
) -> None:
    sha256, byte_size = verify_collision_file(data_dir, manifest_path)
    meta_path = features.with_name("collision-features-v1.meta.json")
    if not meta_path.is_file():
        raise DataError(f"Feature provenance is missing: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise DataError("Feature provenance must be a JSON object")
    assert_feature_provenance(meta, sha256=sha256)
    frame = load_feature_table(features)
    train, validation, test_rows = training_and_validation(frame)
    fitted = fit_baselines(train, validation)
    provenance = {
        "created_at": utc_now(),
        "feature_spec_version": SPEC_VERSION,
        "source_sha256": sha256,
        "source_bytes": byte_size,
        "feature_table": features.name,
        "target_source": "collision_severity",
        "target_output": "severity_serious_or_fatal",
        "positive_codes": ["1", "2"],
        "negative_codes": ["3"],
        "split_policy": {
            "training": ["2021", "2022", "2023"],
            "validation": ["2024"],
            "test": ["2025"],
        },
        "random_seed": SEED,
        "training_rows": int(len(train)),
        "training_years": _years(train),
        "validation_rows": int(len(validation)),
        "validation_years": _years(validation),
        "test_rows_held_out": test_rows,
        "test_year_scored": False,
        "dependencies": dependency_versions(),
    }
    summary = save_run(fitted, output_dir, provenance=provenance)
    report_dir = root / "reports" / "training"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "comparison.json").write_text(
        (output_dir / "comparison.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (report_dir / "comparison.md").write_text(
        (output_dir / "comparison.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    chosen = summary["provisional_model"]
    assert isinstance(chosen, dict)
    logger.info("Provisional model: %s", chosen["model"])
    logger.info("Artifacts: %s", output_dir)
    logger.info("Held out %s test rows", test_rows)


def _select(
    data_dir: Path,
    manifest_path: Path,
    features: Path,
    baselines: Path,
    output_dir: Path,
    root: Path,
    cv_splits: int,
) -> None:
    refuse_existing_evaluation(output_dir)
    provenance = _provenance(data_dir, manifest_path, features)
    frame = load_feature_table(features)
    reference = baselines / "hist_gradient_boosting.joblib"
    frozen = select_from_frame(
        frame,
        reference_path=reference,
        output_dir=output_dir,
        provenance=provenance,
        cv_splits=cv_splits,
    )
    _copy_report(root, output_dir, "selection.md")
    _copy_report(root, output_dir, "frozen-config.json")
    _copy_report(root, output_dir, "calibration-comparison.json")
    _copy_report(root, output_dir, "threshold-comparison.json")
    logger.info("Calibration: %s", frozen["decision"]["calibration_method"])
    logger.info("Threshold: %s", frozen["decision"]["threshold"])
    logger.info("Artifacts: %s", output_dir)


def _evaluate(
    data_dir: Path,
    manifest_path: Path,
    features: Path,
    output_dir: Path,
    root: Path,
) -> None:
    refuse_existing_evaluation(output_dir)
    provenance = _provenance(data_dir, manifest_path, features)
    frame = load_feature_table(features)
    evaluation = evaluate_frozen(frame, output_dir=output_dir, provenance=provenance)
    _copy_report(root, output_dir, "test-evaluation.json")
    _copy_report(root, output_dir, "test-evaluation.md")
    logger.info(
        "2025 rows: %s. Positive rows: %s",
        evaluation["rows"],
        evaluation["positive_rows"],
    )
    logger.info("Artifacts: %s", output_dir)


def _provenance(data_dir: Path, manifest_path: Path, features: Path) -> dict[str, object]:
    sha256, _byte_size = verify_collision_file(data_dir, manifest_path)
    meta_path = features.with_name("collision-features-v1.meta.json")
    if not meta_path.is_file():
        raise DataError(f"Feature provenance is missing: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise DataError("Feature provenance must be a JSON object")
    assert_feature_provenance(meta, sha256=sha256)
    return {
        "source_sha256": sha256,
        "feature_spec_version": SPEC_VERSION,
        "feature_table": features.name,
        "dependencies": dependency_versions(),
    }


def _copy_report(root: Path, output_dir: Path, name: str) -> None:
    report_dir = root / "reports" / "phase6"
    report_dir.mkdir(parents=True, exist_ok=True)
    text = (output_dir / name).read_text(encoding="utf-8")
    (report_dir / name).write_text(text, encoding="utf-8")


def _resolve(root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _years(frame) -> list[str]:
    return sorted(set(frame["collision_year"].astype(str)))


if __name__ == "__main__":
    raise SystemExit(main())
