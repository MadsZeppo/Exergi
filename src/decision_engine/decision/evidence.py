from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ComponentStatus(StrEnum):
    GOOD = "GOOD"
    WARNING = "WARNING"
    BAD = "BAD"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class RecommendationEvidence(StrEnum):
    STRONG = "STRONG_EVIDENCE"
    MODERATE = "MODERATE_EVIDENCE"
    WEAK = "WEAK_EVIDENCE"
    INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


class EvidenceScorecard(BaseModel):
    model_config = ConfigDict(frozen=True)
    forecast_calibration: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    forecast_accuracy: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    treatment_overlap: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    effective_sample_size: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    estimator_agreement: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    covariate_balance: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    placebo_tests: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    negative_controls: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    specification_robustness: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    temporal_stability: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    group_stability: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    confounding_sensitivity: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    distribution_shift: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    missingness: ComponentStatus = ComponentStatus.NOT_AVAILABLE
    extrapolation: ComponentStatus = ComponentStatus.NOT_AVAILABLE

    def recommendation_status(self) -> RecommendationEvidence:
        values = self.model_dump()
        hard = {"treatment_overlap", "estimator_agreement", "placebo_tests", "distribution_shift"}
        if any(values[name] == ComponentStatus.BAD for name in hard):
            return RecommendationEvidence.INSUFFICIENT
        bad = sum(value == ComponentStatus.BAD for value in values.values())
        warning = sum(value == ComponentStatus.WARNING for value in values.values())
        available = sum(value != ComponentStatus.NOT_AVAILABLE for value in values.values())
        if bad or available < 4:
            return RecommendationEvidence.WEAK
        if warning == 0 and available >= 8:
            return RecommendationEvidence.STRONG
        return RecommendationEvidence.MODERATE

    def permits_recommendation(self) -> bool:
        return self.recommendation_status() not in {
            RecommendationEvidence.INSUFFICIENT,
            RecommendationEvidence.WEAK,
        }
