"""Typed public contracts. Timestamps are required to be timezone-aware."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvidenceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Action(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    action_type: str
    discount_pct: float = Field(default=0.0, ge=0, le=100)


class HistoricalDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str
    entity_id: str
    decision_time: datetime
    available_actions: tuple[Action, ...]
    actual_action: Action | None = None
    outcome_start: datetime
    outcome_end: datetime
    target_metric: str

    @field_validator("decision_time", "outcome_start", "outcome_end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def valid_window(self) -> HistoricalDecision:
        if self.outcome_start < self.decision_time or self.outcome_end < self.outcome_start:
            raise ValueError("invalid decision/outcome chronology")
        return self


class DecisionState(BaseModel):
    model_config = ConfigDict(frozen=True)
    features: dict[str, Any]
    generated_at: datetime
    data_cutoff: datetime


class EvidenceStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    overall: EvidenceLevel
    overlap: str = "UNKNOWN"
    calibration: str = "UNKNOWN"
    sample_size: str = "UNKNOWN"
    estimator_agreement: str = "UNKNOWN"
    extrapolation: str = "UNKNOWN"
    missing_features: str = "UNKNOWN"
    warnings: tuple[str, ...] = ()


class ActionOutcomeDistribution(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    expected_value: float
    p05: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float
    std: float = Field(ge=0)
    probability_positive: float = Field(ge=0, le=1)
    probability_beat_baseline: float = Field(ge=0, le=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    evidence_status: EvidenceStatus

    @model_validator(mode="after")
    def ordered(self) -> ActionOutcomeDistribution:
        values = [self.p05, self.p10, self.p25, self.p50, self.p75, self.p90, self.p95]
        if values != sorted(values):
            raise ValueError("quantiles must be nondecreasing")
        return self


class DecisionPrediction(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str
    model_version: str
    created_at: datetime
    data_cutoff: datetime
    action_distributions: tuple[ActionOutcomeDistribution, ...]
    recommended_action: str | None
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    uncertainty_drivers: tuple[str, ...] = ()


class RegretType(StrEnum):
    FACTUAL = "factual_regret"
    MODEL_ESTIMATED = "model_estimated_regret"
    EXPERIMENT_VERIFIED = "experiment_verified_regret"


class PredictionEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str
    actual_action: str | None
    actual_outcome: float
    prediction_error: float | None = None
    interval_coverage: bool | None = None
    regret_type: RegretType | None = None
    regret_value: float | None = Field(default=None, ge=0)
    estimated_value_created: float | None = None
