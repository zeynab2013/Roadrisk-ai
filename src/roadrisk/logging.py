"""Standard-library logging for command-line entry points."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configure the root logger once for a command process."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
