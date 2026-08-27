from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from decision_engine.decision.evidence import EvidenceScorecard, RecommendationEvidence


class DecisionClaim(BaseModel):
    model_config = ConfigDict(frozen=True)
    claim: str
    estimated_difference: float
    uncertainty_interval: tuple[float, float]
    probability_positive: float = Field(ge=0, le=1)
    evidence_status: RecommendationEvidence
    evidence_report: EvidenceScorecard
    supporting_estimators: tuple[str, ...] = ()
    contradicting_estimators: tuple[str, ...] = ()
    falsification_results: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent_with_evidence(self) -> DecisionClaim:
        if self.evidence_status != self.evidence_report.recommendation_status():
            raise ValueError("claim status must be derived from its evidence report")
        if self.uncertainty_interval[0] > self.uncertainty_interval[1]:
            raise ValueError("invalid uncertainty interval")
        return self
