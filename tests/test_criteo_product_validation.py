from __future__ import annotations

import numpy as np

from decision_engine.benchmark.criteo_uplift import (
    masked_policy_value,
    uplift_bin_assignments,
)


def test_gated_policy_value_uses_exact_target_mask() -> None:
    outcome = np.array([1, 0, 1, 0])
    treatment = np.array([1, 0, 1, 0])
    targeted = np.array([True, False, False, False])
    result = masked_policy_value(outcome, treatment, targeted, 0.5)
    assert result["acted_fraction"] == 0.25
    assert result["policy_value"] == 0.5


def test_decile_assignments_are_complete_and_deterministic() -> None:
    score = np.repeat(np.arange(10), 100).astype(float)
    first = uplift_bin_assignments(score)
    second = uplift_bin_assignments(score)
    assert np.array_equal(first, second)
    assert set(first) == set(range(1, 11))
    assert np.all(np.bincount(first)[1:] == 100)
