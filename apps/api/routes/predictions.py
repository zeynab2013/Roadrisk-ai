"""Health, model identity, and one-row prediction routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from apps.api.correlation import accept_correlation_id
from apps.api.schemas import HealthResponse, ModelResponse, PredictionRequest, PredictionResponse
from apps.api.store import save_prediction
from roadrisk.data.errors import DataError
from roadrisk.inference.service import (
    InferenceInputError,
    InferenceSession,
    model_info,
    predict_one,
)
from roadrisk.persistence.repository import PersistenceError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report that the process is up and whether an artifact is loaded."""

    session = request.app.state.session
    if not isinstance(session, InferenceSession):
        return HealthResponse(
            status="ok",
            ready=False,
            detail=str(request.app.state.load_error or "Model artifacts are not loaded"),
        )
    return HealthResponse(
        status="ok",
        ready=True,
        model_version=session.model_version,
        model=str(session.decision.get("model")),
        artifact_role=session.artifact_role,
    )


@router.get("/model", response_model=ModelResponse)
def model(request: Request) -> ModelResponse:
    """Return the loaded artifact's target, threshold, bands, and features."""

    return ModelResponse.model_validate(model_info(require_session(request)))


@router.post("/predictions", response_model=PredictionResponse)
def predict(body: PredictionRequest, request: Request) -> PredictionResponse:
    """Score one reported collision. The body cannot carry a label or an extra field."""

    session = require_session(request)
    try:
        result = predict_one(session, body.model_dump())
    except InferenceInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DataError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        save_prediction(request.app, result)
    except PersistenceError:
        logger.error(
            "prediction history write failed correlation_id=%s",
            _correlation_id(request),
        )
        raise HTTPException(
            status_code=503,
            detail="The prediction could not be stored",
        ) from None
    return PredictionResponse.model_validate(result)


def require_session(request: Request) -> InferenceSession:
    session = request.app.state.session
    if isinstance(session, InferenceSession):
        return session
    detail = str(request.app.state.load_error or "Model artifacts are not loaded")
    raise HTTPException(status_code=503, detail=detail)


def _correlation_id(request: Request) -> str:
    return accept_correlation_id(getattr(request.state, "correlation_id", None))
