from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DecisionDisposition(StrEnum):
    ACT = "ACT"
    EXPERIMENT = "EXPERIMENT"
    ABSTAIN = "ABSTAIN"


class DecisionState(BaseModel):
    model_config = ConfigDict(frozen=True)
    state_id: str
    values: dict[str, Any]
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class CandidateAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class OutcomeDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    unit: str
    higher_is_better: bool = True


class UtilityDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    outcome_weights: dict[str, float]
    risk_aversion: float = Field(default=0.0, ge=0)


class ConstraintDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    operator: str
    threshold: float
    outcome_name: str | None = None


class DecisionHorizon(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> DecisionHorizon:
        if self.end < self.start:
            raise ValueError("horizon end cannot precede start")
        return self


class DecisionContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_time: datetime
    data_cutoff: datetime
    evidence_requirements: tuple[str, ...] = ()

    @field_validator("decision_time", "data_cutoff")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def prevent_future_data(self) -> DecisionContext:
        if self.data_cutoff > self.decision_time:
            raise ValueError("data_cutoff cannot be after decision_time")
        return self


class DecisionProblem(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str
    decision_type: str
    state: DecisionState
    candidate_actions: tuple[CandidateAction, ...]
    target_outcomes: tuple[OutcomeDefinition, ...]
    utility: UtilityDefinition
    constraints: tuple[ConstraintDefinition, ...] = ()
    horizon: DecisionHorizon
    context: DecisionContext

    @model_validator(mode="after")
    def require_candidates_and_outcomes(self) -> DecisionProblem:
        if not self.candidate_actions or not self.target_outcomes:
            raise ValueError("decision problems require actions and outcomes")
        return self


class OutcomeDistribution(BaseModel):
    model_config = ConfigDict(frozen=True)
    outcome_name: str
    mean: float
    p05: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float
    variance: float = Field(ge=0)
    calibration_metadata: dict[str, Any] = Field(default_factory=dict)
    support_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered_quantiles(self) -> OutcomeDistribution:
        quantiles = [self.p05, self.p10, self.p25, self.p50, self.p75, self.p90, self.p95]
        if quantiles != sorted(quantiles):
            raise ValueError("outcome quantiles must be nondecreasing")
        return self


class SimulationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    simulation_id: str
    decision_id: str
    state_snapshot: DecisionState
    candidate_action: CandidateAction
    outcome_distributions: tuple[OutcomeDistribution, ...]
    disposition: DecisionDisposition
    evidence: dict[str, Any]
    support: dict[str, Any]
    uncertainty: dict[str, Any]
    assumptions: tuple[str, ...]
    model_versions: dict[str, str]
    generated_at: datetime
    experiment: dict[str, Any] | None = None

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value
