import numpy as np

from decision_engine.economics.utility import expected_shortfall_lower


def test_lower_tail_expected_shortfall() -> None:
    assert expected_shortfall_lower(np.arange(1, 11), alpha=0.2) == 1.5
