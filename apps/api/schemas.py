"""Request and response models for the prediction API.

The request lists the approved features only. Extra fields are rejected.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from roadrisk.features.spec import APPROVED

PredictionRequest = create_model(
    "PredictionRequest",
    __config__=ConfigDict(extra="forbid"),
    **{
        field.name: (
            float | None if field.data_type == "numeric" else str | None,
            Field(..., description=field.meaning),
        )
        for field in APPROVED
    },
)


class HealthResponse(BaseModel):
    """Process health. ``ready`` is true only when an artifact loaded."""

    status: Literal["ok"]
    ready: bool
    model_version: str | None = None
    model: str | None = None
    artifact_role: str | None = None
    detail: str | None = None


class FeatureInfo(BaseModel):
    name: str
    data_type: str
    meaning: str


class ModelResponse(BaseModel):
    """Identity of the loaded artifact. This route does not score a row."""

    model_version: str
    model: str
    artifact_role: str
    calibration_method: str
    question: str
    not_estimated: str
    positive_class: str
    negative_class: str
    binary_threshold: float
    threshold_policy: str
    risk_level_low_below: float
    risk_level_high_at_or_above: float
    risk_level_inclusivity: str
    risk_levels_are: str
    feature_spec_version: int
    features: list[FeatureInfo]
    feature_count: int


class PredictionHistoryItem(BaseModel):
    """One stored prediction. The feature payload is not part of this record."""

    id: int
    created_at: datetime
    probability: float
    predicted_class: int
    predicted_class_label: Literal["slight", "fatal_or_serious"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    binary_threshold: float
    model_version: str
    model: str
    artifact_role: str
    threshold_policy: str
    question: str
    not_estimated: str
    limitation: str


class PredictionHistoryResponse(BaseModel):
    """Accepted predictions in time order."""

    predictions: list[PredictionHistoryItem]


class AreaGroup(BaseModel):
    """One urban or rural class in a saved model-output summary."""

    area_id: str
    label: str
    collisions: int
    category_counts: dict[str, int]
    category_shares: dict[str, float | None]
    mean_predicted_probability: float | None


class AreaSummaryResponse(BaseModel):
    """Saved Phase 7 summary. It is not an exposure-adjusted safety ranking."""

    grouping_field: str
    grouping_reason: str
    population: str
    minimum_support: int
    rows: int
    missing_location_rows: int
    unsupported_location_rows: int
    groups: list[AreaGroup]
    supported_groups: list[AreaGroup]
    not_estimated: str
    limitation: str


class PredictionResponse(BaseModel):
    """One severity estimate for a reported personal-injury collision."""

    probability: float
    predicted_class: int
    predicted_class_label: Literal["slight", "fatal_or_serious"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    binary_threshold: float
    model_version: str
    model: str
    artifact_role: str
    threshold_policy: str
    question: str
    not_estimated: str
    limitation: str
