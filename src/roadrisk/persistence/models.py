"""SQLAlchemy model for one accepted prediction.

SQLite has no timezone-aware timestamp type. ``created_at`` is stored as
UTC text in the fixed form ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``, which
sorts in time order. The application writes that form and reads it back
as a timezone-aware UTC datetime.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UTC_TIMESTAMP = "%Y-%m-%dT%H:%M:%S.%f+00:00"


class Base(DeclarativeBase):
    """Metadata for the history tables created in one step."""


class PredictionRecord(Base):
    """The prediction the API returned. Feature inputs are not stored."""

    __tablename__ = "prediction_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_class: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_class_label: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)
    binary_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_role: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_policy: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    not_estimated: Mapped[str] = mapped_column(Text, nullable=False)
    limitation: Mapped[str] = mapped_column(Text, nullable=False)


def format_timestamp(value: datetime) -> str:
    """Format one UTC timestamp for the text column."""

    if value.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    return value.astimezone(timezone.utc).strftime(UTC_TIMESTAMP)


def parse_timestamp(value: str) -> datetime:
    """Read a stored UTC timestamp back into an aware datetime."""

    parsed = datetime.strptime(value, UTC_TIMESTAMP)
    return parsed.replace(tzinfo=timezone.utc)
