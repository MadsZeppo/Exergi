import numpy as np

from decision_engine.benchmark.hillstrom_economic import economic_policy_value
from decision_engine.datasets.hillstrom import CONTROL, MENS


def test_economic_policy_subtracts_explicit_contact_cost() -> None:
    spend = np.array([2.0, 1.0, 0.0, 0.0])
    treatment = np.array([MENS, CONTROL, MENS, CONTROL])
    targeted = np.array([True, False, True, False])
    result = economic_policy_value(spend, treatment, targeted, contact_cost=0.5, propensity=0.5)
    assert result["gross_outcome_value"] == 1.5
    assert result["treatment_cost"] == 0.25
    assert result["net_policy_value"] == 1.25


def test_treat_none_has_zero_treatment_cost() -> None:
    spend = np.array([1.0, 2.0])
    treatment = np.array([MENS, CONTROL])
    result = economic_policy_value(
        spend,
        treatment,
        np.zeros(2, dtype=bool),
        contact_cost=10.0,
        propensity=0.5,
    )
    assert result["treatment_cost"] == 0
