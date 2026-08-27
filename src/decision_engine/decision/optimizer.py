from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from decision_engine.economics.utility import risk_adjusted_utility
from decision_engine.schemas import EvidenceLevel, EvidenceStatus


@dataclass(frozen=True)
class DecisionConstraints:
    maximum_discount: float | None = None
    minimum_probability_beat_baseline: float = 0.0
    maximum_downside_probability: float = 1.0
    minimum_expected_margin: float | None = None


def optimize_action(
    profit_samples: dict[str, np.ndarray],
    evidence: dict[str, EvidenceStatus],
    *,
    baseline_action: str,
    discounts: dict[str, float],
    constraints: DecisionConstraints | None = None,
    risk_aversion: float = 0.0,
) -> str | None:
    constraints = constraints or DecisionConstraints()
    baseline = profit_samples[baseline_action]
    feasible: list[tuple[float, str]] = []
    for action, samples in profit_samples.items():
        if evidence[action].overall == EvidenceLevel.INSUFFICIENT_EVIDENCE:
            continue
        if (
            constraints.maximum_discount is not None
            and discounts[action] > constraints.maximum_discount
        ):
            continue
        probability_beat = float(np.mean(samples > baseline))
        probability_downside = float(np.mean(samples < baseline))
        if probability_beat < constraints.minimum_probability_beat_baseline:
            continue
        if probability_downside > constraints.maximum_downside_probability:
            continue
        if (
            constraints.minimum_expected_margin is not None
            and float(np.mean(samples)) < constraints.minimum_expected_margin
        ):
            continue
        feasible.append((risk_adjusted_utility(samples, risk_aversion), action))
    return max(feasible)[1] if feasible else None
