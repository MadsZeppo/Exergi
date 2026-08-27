from decision_engine.robustness.sensitivity import linear_partial_r2_sensitivity


def test_sensitivity_is_monotonic_in_confounding_strength() -> None:
    weak = linear_partial_r2_sensitivity(2, 0.2, 100, partial_r2_y=0.01, partial_r2_treatment=0.01)
    strong = linear_partial_r2_sensitivity(2, 0.2, 100, partial_r2_y=0.2, partial_r2_treatment=0.2)
    assert abs(strong.adjusted_effect) < abs(weak.adjusted_effect)
    assert weak.robustness_value == strong.robustness_value
