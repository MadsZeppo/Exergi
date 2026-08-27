import numpy as np

from decision_engine.causal.ope import (
    clipped_dr_value,
    dr_value,
    ips_value,
    ope_diagnostics,
    snips_value,
)
from decision_engine.decision.anytime import hoeffding_confidence_sequence
from decision_engine.decision.value_of_information import NormalActionEvidence, monte_carlo_evsi
from decision_engine.economics.utility import contribution_profit_utility, downside_cvar_loss


def test_evsi_is_zero_when_action_is_known_and_test_has_cost() -> None:
    result = monte_carlo_evsi(
        (NormalActionEvidence(-2.0, 0.0),),
        future_population=10_000,
        relevance=1.0,
        sample_size=500,
        outcome_standard_deviation=1.0,
        experiment_cost=10.0,
    )
    assert result.population_evsi == 0
    assert not result.test_allowed


def test_evsi_is_positive_for_reusable_uncertain_decision() -> None:
    result = monte_carlo_evsi(
        (NormalActionEvidence(0.0, 1.0),),
        future_population=100_000,
        relevance=0.8,
        sample_size=500,
        outcome_standard_deviation=1.0,
        experiment_cost=20.0,
    )
    assert result.conservative_enbs > 0
    assert result.test_allowed


def test_anytime_null_does_not_promote() -> None:
    values = np.tile(np.array([-1.0, 1.0]), 500)
    result = hoeffding_confidence_sequence(values, lower_bound=-1, upper_bound=1)
    assert result.promoted_at is None


def test_anytime_positive_sequence_promotes() -> None:
    values = np.full(2000, 0.5)
    result = hoeffding_confidence_sequence(values, lower_bound=-1, upper_bound=1)
    assert result.promoted_at is not None


def test_ope_recovers_on_policy_value_under_equal_propensity() -> None:
    reward = np.array([0.0, 1.0, 0.0, 1.0])
    weights = np.ones(4)
    assert ips_value(reward, weights) == 0.5
    assert snips_value(reward, weights) == 0.5
    assert dr_value(reward, weights, np.full(4, 0.5), np.full(4, 0.5)) == 0.5
    assert clipped_dr_value(reward, weights, np.full(4, 0.5), np.full(4, 0.5), clip=1) == 0.5


def test_propensity_failure_is_visible_in_diagnostics() -> None:
    diagnostics = ope_diagnostics(np.array([1.0, 1.0, 100.0]), np.array([0.5, 0.5, 0.0]))
    assert diagnostics.effective_sample_size < 2
    assert diagnostics.unsupported_fraction > 0
    assert diagnostics.maximum_weight == 100


def test_profit_utility_penalizes_lower_tail() -> None:
    values = np.array([-10.0, 2.0, 2.0, 2.0, 2.0])
    assert downside_cvar_loss(values, alpha=0.2) == 10
    assert contribution_profit_utility(values, risk_aversion=1, alpha=0.2) < np.mean(values)
