"""Load the frozen Phase 6 pipeline without rewriting it."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from roadrisk.data.errors import DataError
from roadrisk.training.phase6 import (
    FROZEN_CONFIG,
    SELECTED_ARTIFACT,
    decision_hash,
    file_sha256,
)
from roadrisk.training.scoring import load_estimator

PHASE7_DIR_NAME = "phase7-v1"
RISK_BANDS_FILE = "risk-bands.json"


def load_frozen_model(phase6_dir: Path):
    """Return the calibrated pipeline and its decision.

    The directory is read only. A missing or hash-mismatched artifact raises.
    """

    frozen_path = phase6_dir / FROZEN_CONFIG
    if not frozen_path.is_file():
        raise DataError(f"Frozen configuration is missing: {frozen_path}")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if not isinstance(frozen, dict):
        raise DataError("Frozen configuration must be a JSON object")
    decision = frozen.get("decision")
    if not isinstance(decision, Mapping):
        raise DataError("Frozen configuration is missing a decision")
    expected = str(frozen.get("decision_sha256"))
    if decision_hash(decision) != expected:
        raise DataError("Frozen decision hash does not match the configuration")
    artifact_name = str(decision.get("selected_artifact") or SELECTED_ARTIFACT)
    artifact = phase6_dir / artifact_name
    actual = file_sha256(artifact) if artifact.is_file() else None
    if actual != decision.get("selected_artifact_sha256"):
        raise DataError(f"Frozen pipeline hash does not match the configuration: {artifact}")
    return load_estimator(artifact), decision
