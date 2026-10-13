"""Create and list prediction history records.

Queries stay here. The inference service does not import this module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from roadrisk.persistence.models import Base, PredictionRecord, format_timestamp, parse_timestamp

STORED_FIELDS = (
    "probability",
    "predicted_class",
    "predicted_class_label",
    "risk_level",
    "binary_threshold",
    "model_version",
    "model",
    "artifact_role",
    "threshold_policy",
    "question",
    "not_estimated",
    "limitation",
)


class PersistenceError(Exception):
    """History could not be saved or read."""


class HistoryRepository:
    """One engine and the schema it owns."""

    def __init__(self, database_url: str) -> None:
        _prepare_sqlite_parent(database_url)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        try:
            self.engine = create_engine(database_url, connect_args=connect_args)
            self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
            Base.metadata.create_all(self.engine)
        except Exception as exc:
            raise PersistenceError("Prediction history storage is unavailable") from exc

    def add(
        self, prediction: dict[str, object], *, created_at: datetime | None = None
    ) -> dict[str, object]:
        """Insert one accepted prediction. The caller has already scored it."""

        stamp = _utc(created_at)
        row = PredictionRecord(created_at=format_timestamp(stamp))
        for name in STORED_FIELDS:
            if name not in prediction:
                raise PersistenceError("Prediction history storage is unavailable")
            setattr(row, name, prediction[name])
        try:
            with self._session_factory() as session:
                session.add(row)
                session.commit()
                session.refresh(row)
                return _public(row)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("Prediction history storage is unavailable") from exc

    def list_records(self) -> list[dict[str, object]]:
        """Return every stored prediction, oldest first, then by id."""

        statement = select(PredictionRecord).order_by(
            PredictionRecord.created_at.asc(),
            PredictionRecord.id.asc(),
        )
        try:
            with self._session_factory() as session:
                rows = session.scalars(statement).all()
                return [_public(row) for row in rows]
        except Exception as exc:
            raise PersistenceError("Prediction history storage is unavailable") from exc


def _public(row: PredictionRecord) -> dict[str, object]:
    return {
        "id": row.id,
        "created_at": parse_timestamp(row.created_at),
        "probability": row.probability,
        "predicted_class": row.predicted_class,
        "predicted_class_label": row.predicted_class_label,
        "risk_level": row.risk_level,
        "binary_threshold": row.binary_threshold,
        "model_version": row.model_version,
        "model": row.model,
        "artifact_role": row.artifact_role,
        "threshold_policy": row.threshold_policy,
        "question": row.question,
        "not_estimated": row.not_estimated,
        "limitation": row.limitation,
    }


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise PersistenceError("Prediction history storage is unavailable")
    return value.astimezone(timezone.utc)


def _prepare_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return
    if ":memory:" in database_url or database_url in {"sqlite://", "sqlite:///"}:
        return
    raw = database_url.removeprefix("sqlite:///")
    if not raw or raw.startswith(":memory:"):
        return
    Path(raw).parent.mkdir(parents=True, exist_ok=True)
