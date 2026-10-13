"""Process configuration loaded once at the command boundary."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Paths and log level for one command.

    Attributes:
        project_root: Repository root used to resolve relative paths.
        data_dir: Root of ``raw``, ``processed``, ``external``, and ``models``.
        log_level: Standard-library level name.
    """

    project_root: Path
    data_dir: Path
    log_level: str


def load_settings(
    environ: Mapping[str, str] | None = None,
    *,
    project_root: Path | None = None,
) -> Settings:
    """Build settings from the environment.

    ``ROADRISK_DATA_DIR`` may be absolute or relative to ``project_root``.
    The default directory is ``data`` under that root. ``ROADRISK_LOG_LEVEL``
    defaults to ``INFO``.
    """

    env = os.environ if environ is None else environ
    root = (project_root or Path.cwd()).resolve()
    configured = env.get("ROADRISK_DATA_DIR", "data")
    data_dir = Path(configured)
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    log_level = env.get("ROADRISK_LOG_LEVEL", "INFO").upper()
    return Settings(project_root=root, data_dir=data_dir.resolve(), log_level=log_level)


def database_url(
    environ: Mapping[str, str] | None = None,
    *,
    project_root: Path | None = None,
) -> str:
    """Return ``ROADRISK_DATABASE_URL`` or a SQLite file under the data directory.

    The default path is ``data/roadrisk.sqlite3`` relative to the project
    root. It contains no credentials. A configured URL is used unchanged,
    so a later deployment can point the same setting at another database.
    """

    env = os.environ if environ is None else environ
    configured = env.get("ROADRISK_DATABASE_URL")
    if configured:
        return configured
    settings = load_settings(env, project_root=project_root)
    path = (settings.data_dir / "roadrisk.sqlite3").resolve()
    return "sqlite:///" + path.as_posix()
