"""Held-out policy-complexity promotion for V6."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from commercial_twin.progressive_decision import PolicyGranularity


@dataclass(frozen=True)
class ComplexityPromotionReport:
    from_level: PolicyGranularity
    to_level: PolicyGranularity
    incremental_value: float
    standard_error: float
    lower: float
    effective_sample_size: float
    heterogeneity_supported: bool
    stable: bool
    economically_material: bool
    promoted: bool


def evaluate_complexity_promotion(
    incremental_policy_scores: np.ndarray,
    *,
    from_level: PolicyGranularity,
    to_level: PolicyGranularity,
    effective_sample_size: float,
    minimum_effective_sample_size: float,
    heterogeneity_supported: bool,
    stable: bool,
    economic_materiality: float,
) -> ComplexityPromotionReport:
    values = np.asarray(incremental_policy_scores, dtype=float)
    if len(values) < 2:
        raise ValueError("held-out promotion requires at least two scores")
    mean = float(np.mean(values))
    se = float(np.std(values, ddof=1) / np.sqrt(len(values)))
    lower = mean - 1.96 * se
    material = lower > economic_materiality
    promoted = (
        lower > 0
        and effective_sample_size >= minimum_effective_sample_size
        and heterogeneity_supported
        and stable
        and material
    )
    return ComplexityPromotionReport(
        from_level=from_level,
        to_level=to_level,
        incremental_value=mean,
        standard_error=se,
        lower=lower,
        effective_sample_size=effective_sample_size,
        heterogeneity_supported=heterogeneity_supported,
        stable=stable,
        economically_material=material,
        promoted=promoted,
    )
