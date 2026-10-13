"""Request correlation IDs for the HTTP process.

A caller may send ``X-Correlation-ID``. The value is kept only when it is
1 to 64 characters from the set ``A-Z``, ``a-z``, ``0-9``, ``.``, ``_``,
and ``-``. Anything else, including a missing header, a newline, or a
longer value, is replaced with a new identifier. The chosen value is
returned on the response and written on failure logs. Request bodies are
not written.
"""

from __future__ import annotations

import logging
import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"
_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def accept_correlation_id(raw: str | None) -> str:
    """Return a safe correlation ID. Invalid input is discarded."""

    if raw is not None and _PATTERN.fullmatch(raw):
        return raw
    return uuid.uuid4().hex


class CorrelationIdMiddleware:
    """Attach one correlation ID to each HTTP request and its response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header = _header(scope, CORRELATION_HEADER)
        correlation_id = accept_correlation_id(header)
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["correlation_id"] = correlation_id
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message["headers"])
                headers.append((CORRELATION_HEADER.lower().encode(), correlation_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.error(
                "request failed method=%s path=%s status=500 correlation_id=%s",
                scope.get("method", ""),
                scope.get("path", ""),
                correlation_id,
            )
            raise
        if status_code >= 400:
            logger.error(
                "request failed method=%s path=%s status=%s correlation_id=%s",
                scope.get("method", ""),
                scope.get("path", ""),
                status_code,
                correlation_id,
            )


def _header(scope: Scope, name: str) -> str | None:
    target = name.lower().encode()
    for key, value in scope.get("headers", []):
        if key.lower() == target:
            return value.decode("latin-1")
    return None
