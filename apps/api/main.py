"""RoadRisk HTTP service.

Start from the repository root:

    python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

The process reads the frozen Phase 6 pipeline and the Phase 7 band file.
It does not train a replacement when those files are missing.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.correlation import CORRELATION_HEADER, CorrelationIdMiddleware
from apps.api.routes.areas import router as areas_router
from apps.api.routes.history import router as history_router
from apps.api.routes.predictions import router
from roadrisk.config import database_url as default_database_url
from roadrisk.data.errors import DataError
from roadrisk.inference.service import InferenceSession, load_default_session

logger = logging.getLogger(__name__)

DESCRIPTION = (
    "Estimates whether a reported personal-injury collision was fatal or "
    "serious rather than slight. It does not estimate whether a collision occurs, "
    "and LOW, MEDIUM, and HIGH are research bands for that severity probability."
)


def create_app(
    session: InferenceSession | None = None,
    *,
    load: bool = True,
    database_url: str | None = None,
) -> FastAPI:
    """Build the application.

    Pass ``session`` in tests. When ``session`` is omitted and ``load`` is
    true, the process opens the configured artifact paths. A missing artifact
    leaves the process up and the scoring routes unavailable.

    ``database_url`` selects a database for one process, usually a temporary
    SQLite file in tests. The history file is not created here.
    """

    app = FastAPI(title="RoadRisk", version="0.1.0", description=DESCRIPTION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", CORRELATION_HEADER],
        expose_headers=[CORRELATION_HEADER],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.state.session = None
    app.state.load_error = None
    app.state.database_url = database_url or default_database_url()
    app.state.history = None
    if session is not None:
        app.state.session = session
    elif load:
        try:
            app.state.session = load_default_session()
        except DataError:
            logger.error("model artifacts could not be loaded")
            app.state.load_error = "Model artifacts are not loaded"
    else:
        app.state.load_error = "Model artifacts were not loaded"
    app.include_router(router)
    app.include_router(history_router)
    app.include_router(areas_router)
    return app


def _cors_origins() -> list[str]:
    configured = os.environ.get(
        "ROADRISK_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    return [item.strip() for item in configured.split(",") if item.strip()]


app = create_app()
