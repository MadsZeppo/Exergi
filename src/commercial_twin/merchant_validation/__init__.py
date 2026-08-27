"""Merchant-scoped validation product services."""

from .contracts import (
    ActionRecommendation,
    CapabilityMatrix,
    DataHealthReport,
    DecisionCard,
    EvidenceLabel,
    ExperimentSpec,
    MerchantCustomerTwin,
    Opportunity,
)
from .learning import HistoricalEvidenceMatcher, HistoricalSupport, LearnedRecommendation
from .service import MerchantValidationService, build_demo_service

__all__ = [
    "ActionRecommendation",
    "CapabilityMatrix",
    "DataHealthReport",
    "DecisionCard",
    "EvidenceLabel",
    "ExperimentSpec",
    "MerchantCustomerTwin",
    "MerchantValidationService",
    "HistoricalEvidenceMatcher",
    "HistoricalSupport",
    "LearnedRecommendation",
    "Opportunity",
    "build_demo_service",
]
