from __future__ import annotations

from dataclasses import dataclass

from decision_engine.schemas import EvidenceLevel, EvidenceStatus


@dataclass(frozen=True)
class EvidenceInputs:
    min_propensity: float
    comparable_count: int
    sample_size: int
    calibration_error: float
    extrapolation_distance: float
    estimator_disagreement: float
    missing_feature_rate: float


def assess_evidence(
    inputs: EvidenceInputs,
    *,
    insufficient_propensity: float = 0.01,
    low_propensity: float = 0.05,
    minimum_samples: int = 100,
    minimum_comparables: int = 20,
) -> EvidenceStatus:
    warnings: list[str] = []
    insufficient = (
        inputs.min_propensity < insufficient_propensity
        or inputs.comparable_count < minimum_comparables
    )
    if inputs.min_propensity < low_propensity:
        warnings.append("treatment has weak historical support")
    if inputs.sample_size < minimum_samples:
        warnings.append("sample size below configured threshold")
    if inputs.missing_feature_rate > 0.2:
        warnings.append("high missing feature rate")
    weak_count = sum(
        [
            inputs.min_propensity < low_propensity,
            inputs.sample_size < minimum_samples,
            inputs.calibration_error > 0.1,
            inputs.extrapolation_distance > 2.0,
            inputs.estimator_disagreement > 0.25,
            inputs.missing_feature_rate > 0.1,
        ]
    )
    if insufficient:
        overall = EvidenceLevel.INSUFFICIENT_EVIDENCE
    elif weak_count >= 3:
        overall = EvidenceLevel.LOW
    elif weak_count:
        overall = EvidenceLevel.MEDIUM
    else:
        overall = EvidenceLevel.HIGH
    return EvidenceStatus(
        overall=overall,
        overlap="LOW" if inputs.min_propensity < low_propensity else "GOOD",
        calibration="LOW" if inputs.calibration_error > 0.1 else "GOOD",
        sample_size="LOW" if inputs.sample_size < minimum_samples else "GOOD",
        estimator_agreement="LOW" if inputs.estimator_disagreement > 0.25 else "GOOD",
        extrapolation="LOW" if inputs.extrapolation_distance > 2 else "GOOD",
        missing_features="LOW" if inputs.missing_feature_rate > 0.1 else "GOOD",
        warnings=tuple(warnings),
    )
