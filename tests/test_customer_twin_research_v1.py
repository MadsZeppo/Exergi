from __future__ import annotations

import numpy as np
import pytest

from commercial_twin.research_v1 import (
    BenchmarkAuthority,
    ResearchMode,
    doubly_robust_policy_value,
    effective_sample_size,
    energy_score,
    exponential_point_process_nll,
    importance_weights,
    ips,
    multiarm_aipw_components,
    snips,
    time_rescaling_residuals,
)


@pytest.mark.parametrize(
    "mode", [ResearchMode.AUDIT, ResearchMode.QUICK, ResearchMode.DEVELOPMENT, ResearchMode.FREEZE]
)
def test_only_official_mode_can_reveal(mode: ResearchMode) -> None:
    with pytest.raises(PermissionError):
        BenchmarkAuthority(mode).require_official("read final outcomes")
    BenchmarkAuthority(ResearchMode.OFFICIAL).require_official("read final outcomes")


def test_point_process_likelihood_includes_integral_and_censoring() -> None:
    result = exponential_point_process_nll(np.array([1.0, 2.0]), np.array([2.0, 2.0]), 3.0)
    assert result == pytest.approx(12.0 - 2 * np.log(2.0))
    assert np.allclose(time_rescaling_residuals(np.array([1.0, 2.0]), np.array([2.0, 3.0])), [2, 6])


def test_energy_score_is_zero_for_perfect_degenerate_forecast() -> None:
    assert energy_score(np.ones((5, 2)), np.ones(2)) == 0


def test_ope_estimators_and_ess_exact_toy() -> None:
    reward = np.array([1.0, 0.0])
    weights = importance_weights(np.array([0.5, 0.5]), np.array([1.0, 0.0]))
    assert np.allclose(weights, [2, 0])
    assert ips(reward, weights) == 1
    assert snips(reward, weights) == 1
    assert effective_sample_size(weights) == 1
    assert doubly_robust_policy_value(reward, weights, np.zeros(2), np.zeros(2)) == 1


def test_multiarm_aipw_recovers_observed_residual_correction() -> None:
    score = multiarm_aipw_components(
        np.array([1.0, 0.0]),
        np.array([0, 1]),
        np.full((2, 2), 0.5),
        np.full((2, 2), 0.5),
    )
    assert np.allclose(score, [[1.5, 0.5], [0.5, -0.5]])


def test_zero_logged_support_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        importance_weights(np.array([0.0]), np.array([1.0]))
