from decision_engine.causal.agreement import estimator_agreement
from decision_engine.decision.evidence import (
    ComponentStatus,
    EvidenceScorecard,
    RecommendationEvidence,
)


def test_sign_disagreement_withholds_recommendation() -> None:
    agreement = estimator_agreement({"dr": {"promo": 10}, "fixed": {"promo": -2}})
    assert agreement.status == "CONTRADICTORY"
    scorecard = EvidenceScorecard(
        treatment_overlap=ComponentStatus.GOOD,
        estimator_agreement=ComponentStatus.BAD,
        placebo_tests=ComponentStatus.GOOD,
        distribution_shift=ComponentStatus.GOOD,
    )
    assert scorecard.recommendation_status() == RecommendationEvidence.INSUFFICIENT
    assert not scorecard.permits_recommendation()
