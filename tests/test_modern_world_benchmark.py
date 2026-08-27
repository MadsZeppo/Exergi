from __future__ import annotations

import numpy as np

from domains.commerce.modern_world_benchmark import _sample_weights


def test_recency_weights_are_deterministic_and_monotone() -> None:
    dates = np.array(["2024-01-01", "2024-07-01", "2025-01-01"], dtype="datetime64[D]")
    weights = _sample_weights(dates, 6)
    assert np.all(np.diff(weights) > 0)
    assert weights[-1] == 1.0
    assert np.array_equal(_sample_weights(dates, None), np.ones(3))
