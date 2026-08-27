import numpy as np

from decision_engine.economics.profit import contribution_profit


def test_contribution_profit() -> None:
    assert contribution_profit(10, 4, 3, 2) == 16
    assert np.array_equal(
        contribution_profit(np.array([10, 8]), 4, np.array([2, 3])), np.array([12, 12])
    )
