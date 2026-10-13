"""List accepted predictions. Clients cannot supply a query or a file path."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from apps.api.correlation import accept_correlation_id
from apps.api.schemas import PredictionHistoryResponse
from apps.api.store import read_predictions
from roadrisk.persistence.repository import PersistenceError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/predictions", response_model=PredictionHistoryResponse)
def list_predictions(request: Request) -> PredictionHistoryResponse:
    """Return stored predictions, oldest first, then by record id."""

    try:
        rows = read_predictions(request.app)
    except PersistenceError:
        logger.error(
            "prediction history read failed correlation_id=%s",
            accept_correlation_id(getattr(request.state, "correlation_id", None)),
        )
        raise HTTPException(status_code=503, detail="Prediction history is unavailable") from None
    return PredictionHistoryResponse.model_validate({"predictions": rows})
