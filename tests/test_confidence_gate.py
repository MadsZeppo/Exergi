import numpy as np

from decision_engine.decision.confidence import EvidenceInputs, assess_evidence
from decision_engine.decision.optimizer import optimize_action
from decision_engine.schemas import EvidenceLevel


def test_unsupported_treatment_is_not_recommended() -> None:
    insufficient = assess_evidence(EvidenceInputs(0.001, 2, 1000, 0.02, 0.1, 0.1, 0.0))
    good = assess_evidence(EvidenceInputs(0.2, 100, 1000, 0.02, 0.1, 0.1, 0.0))
    assert insufficient.overall == EvidenceLevel.INSUFFICIENT_EVIDENCE
    chosen = optimize_action(
        {"none": np.array([1.0, 1.0]), "promo": np.array([10.0, 10.0])},
        {"none": good, "promo": insufficient},
        baseline_action="none",
        discounts={"none": 0, "promo": 20},
    )
    assert chosen == "none"
