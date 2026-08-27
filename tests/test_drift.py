import numpy as np

from decision_engine.robustness.drift import distribution_shift_report


def test_severe_regime_shift_is_detected() -> None:
    rng = np.random.default_rng(42)
    report = distribution_shift_report(
        {"demand": rng.normal(0, 1, 1000)}, {"demand": rng.normal(5, 1, 1000)}
    )
    assert report.overall == "SEVERE"
