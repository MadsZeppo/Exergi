import numpy as np
import pytest

from decision_engine.metrics.probabilistic import (
    crps_ensemble,
    interval_score,
    weighted_interval_score,
)


def test_interval_score_penalizes_misses_and_width() -> None:
    y = np.array([0.0])
    assert interval_score(y, np.array([-1.0]), np.array([1.0]), 0.2).item() == 2
    assert interval_score(np.array([2.0]), np.array([-1.0]), np.array([1.0]), 0.2).item() == 12


def test_wis_known_single_interval() -> None:
    score = weighted_interval_score(
        np.array([0.0]), np.array([0.0]), {0.2: (np.array([-1.0]), np.array([1.0]))}
    )
    assert score == pytest.approx(0.2 / 1.5)


def test_crps_degenerate_and_two_point_distribution() -> None:
    assert crps_ensemble(np.array([2.0]), np.array([[2.0, 2.0]])) == 0
    assert crps_ensemble(np.array([0.0]), np.array([[-1.0, 1.0]])) == pytest.approx(0.5)
