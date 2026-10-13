"""Open the history repository for the API process.

The inference service does not import this module. A repository is created
on the first history read or write, not when the API module is imported.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from roadrisk.persistence.repository import HistoryRepository, PersistenceError

logger = logging.getLogger(__name__)


def repository_for(app: FastAPI) -> HistoryRepository:
    """Return the process repository, creating the schema on first use."""

    current = getattr(app.state, "history", None)
    if isinstance(current, HistoryRepository):
        return current
    if current is not None:
        return current
    try:
        repository = HistoryRepository(str(app.state.database_url))
    except PersistenceError:
        logger.error("prediction history storage could not be opened")
        raise
    app.state.history = repository
    return repository


def save_prediction(app: FastAPI, prediction: dict[str, object]) -> None:
    """Store one scored prediction. Raises when the write does not commit."""

    repository_for(app).add(prediction)


def read_predictions(app: FastAPI) -> list[dict[str, object]]:
    """List stored predictions. Raises when the database cannot be read."""

    return repository_for(app).list_records()
