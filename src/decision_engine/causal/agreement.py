from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EstimatorAgreement:
    standard_deviation: float
    coefficient_of_dispersion: float
    sign_agreement: float
    rank_agreement: float
    status: str


def estimator_agreement(estimates: dict[str, dict[str, float]]) -> EstimatorAgreement:
    if len(estimates) < 2:
        raise ValueError("at least two estimators are required")
    actions = sorted(set.intersection(*(set(item) for item in estimates.values())))
    if not actions:
        raise ValueError("estimators have no common actions")
    matrix = np.array(
        [[estimates[name][action] for action in actions] for name in sorted(estimates)]
    )
    standard_deviation = float(np.mean(np.std(matrix, axis=0)))
    coefficient = standard_deviation / max(float(np.mean(np.abs(matrix))), 1e-12)
    signs = np.sign(matrix)
    sign_agreement = float(
        np.mean(
            np.max(
                [
                    np.mean(signs == -1, axis=0),
                    np.mean(signs == 0, axis=0),
                    np.mean(signs == 1, axis=0),
                ],
                axis=0,
            )
        )
    )
    rankings = np.argsort(np.argsort(matrix, axis=1), axis=1)
    correlations = (
        [
            np.corrcoef(rankings[i], rankings[j])[0, 1]
            for i in range(len(rankings))
            for j in range(i)
        ]
        if len(actions) > 1
        else []
    )
    rank_agreement = float(np.mean(correlations)) if correlations else 1.0
    if sign_agreement < 1:
        status = "CONTRADICTORY"
    elif coefficient > 0.5 or rank_agreement < 0.5:
        status = "WEAK"
    elif coefficient > 0.2 or rank_agreement < 0.8:
        status = "MODERATE"
    else:
        status = "STRONG"
    return EstimatorAgreement(
        standard_deviation, coefficient, sign_agreement, rank_agreement, status
    )
