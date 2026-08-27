import numpy as np

from decision_engine.forecasting.quantile_model import repair_crossing_quantiles


def test_quantile_repair_and_crossing_rate() -> None:
    repaired, rate = repair_crossing_quantiles(np.array([[3, 2, 1], [1, 2, 3]], dtype=float))
    assert rate == 0.5
    assert np.all(np.diff(repaired, axis=1) >= 0)
