"""Read the saved Phase 7 area summary. This route does not score rows."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from apps.api.correlation import accept_correlation_id
from apps.api.routes.predictions import require_session
from apps.api.schemas import AreaSummaryResponse
from roadrisk.inference.service import artifact_paths

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/area-summaries", response_model=AreaSummaryResponse)
def area_summaries(request: Request) -> AreaSummaryResponse:
    """Return the saved urban/rural model-output summary for the loaded decision."""

    session = require_session(request)
    summary_path, bands_path = _summary_paths()
    try:
        payload = _load_summary(summary_path, bands_path, session.decision_sha256)
    except FileNotFoundError:
        logger.error(
            "area summary file is missing correlation_id=%s",
            _correlation_id(request),
        )
        raise HTTPException(status_code=503, detail="Area summary is not available") from None
    except ValueError:
        logger.error(
            "area summary could not be read correlation_id=%s",
            _correlation_id(request),
        )
        raise HTTPException(status_code=503, detail="Area summary is not available") from None
    except PermissionError:
        logger.error(
            "area summary is not tied to the loaded model correlation_id=%s",
            _correlation_id(request),
        )
        raise HTTPException(
            status_code=409,
            detail="Area summary is not tied to the loaded model",
        ) from None
    return AreaSummaryResponse.model_validate(payload)


def _correlation_id(request: Request) -> str:
    return accept_correlation_id(getattr(request.state, "correlation_id", None))


def _summary_paths() -> tuple[Path, Path]:
    _phase6_dir, bands_path = artifact_paths()
    return bands_path.parent / "group-summary.json", bands_path


def _load_summary(summary_path: Path, bands_path: Path, decision_sha256: str) -> dict[str, object]:
    if not summary_path.is_file() or not bands_path.is_file():
        raise FileNotFoundError
    try:
        bands = json.loads(bands_path.read_text(encoding="utf-8"))
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError from exc
    if not isinstance(bands, dict) or not isinstance(payload, dict):
        raise ValueError
    if bands.get("decision_sha256") != decision_sha256:
        raise PermissionError
    if payload.get("grouping_field") != "urban_or_rural_area":
        raise ValueError
    return payload
