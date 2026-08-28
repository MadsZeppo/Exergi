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
from .design_partner_contract import (
    MerchantPilotValidationReport,
    MerchantShadowPilotRow,
    MerchantShadowPilotSchema,
    PilotStage,
    PretreatmentFeature,
    ReadOnlyPilotProtocol,
    validate_shadow_pilot,
)
from .economics_contract import MerchantEconomicOutcome
from .learning import HistoricalEvidenceMatcher, HistoricalSupport, LearnedRecommendation
from .rct_protocol import CommercialEvidenceGate, MerchantRCTProtocol, PilotArm
from .service import MerchantValidationService, build_demo_service
from .shadow_policy import ShadowDecision, ShadowPolicy

__all__ = [
    "ActionRecommendation",
    "CapabilityMatrix",
    "CommercialEvidenceGate",
    "DataHealthReport",
    "DecisionCard",
    "EvidenceLabel",
    "ExperimentSpec",
    "MerchantCustomerTwin",
    "MerchantEconomicOutcome",
    "MerchantPilotValidationReport",
    "MerchantShadowPilotRow",
    "MerchantShadowPilotSchema",
    "MerchantRCTProtocol",
    "MerchantValidationService",
    "HistoricalEvidenceMatcher",
    "HistoricalSupport",
    "LearnedRecommendation",
    "Opportunity",
    "PilotArm",
    "PilotStage",
    "PretreatmentFeature",
    "ReadOnlyPilotProtocol",
    "ShadowDecision",
    "ShadowPolicy",
    "build_demo_service",
    "validate_shadow_pilot",
]
