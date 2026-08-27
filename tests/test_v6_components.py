import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from commercial_twin.progressive_decision import PolicyGranularity, default_action_banks
from decision_engine.causal.hierarchical import (
    NormalEffect,
    TransportSupport,
    partial_pool,
    transport_report,
)
from decision_engine.causal.variance_reduction import cupac_adjust_oof, cuped_adjust
from decision_engine.decision.anytime_v6 import empirical_bernstein_confidence_sequence
from decision_engine.decision.experiment_design import (
    EnrollmentStrategy,
    logged_assignment,
    neyman_allocation,
    optimize_experiment,
)
from decision_engine.decision.high_value import potential_decision_value
from decision_engine.decision.progressive import evaluate_complexity_promotion
from decision_engine.decision.value_of_information import NormalActionEvidence

ROOT = Path(__file__).parents[1]


def test_v1_v5_official_artifacts_are_immutable() -> None:
    manifest = json.loads(
        (ROOT / "benchmarks/ecommerce_decision_layer_v6/LEGACY_ARTIFACT_MANIFEST.json").read_text()
    )
    for relative, expected in manifest.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_action_banks_are_bounded_and_have_bau() -> None:
    banks = default_action_banks()
    assert len(banks) == 4
    assert all(2 <= len(bank) <= 5 for bank in banks.values())
    assert all(sum(action.is_bau for action in bank) == 1 for bank in banks.values())


def test_high_value_gate_rejects_zero_and_accepts_reusable_value() -> None:
    zero = potential_decision_value(
        eligible_exposures=100,
        action_frequency=0.1,
        contribution_profit_scale=10,
        plausible_effect_mean=0,
        plausible_effect_standard_error=0,
        remaining_horizon=5,
        expected_reuse=1,
        freshness_weight=1,
        reversibility=1,
        downside=0,
        action_cost=1,
        materiality_threshold=100,
    )
    valuable = potential_decision_value(
        eligible_exposures=10_000,
        action_frequency=0.5,
        contribution_profit_scale=20,
        plausible_effect_mean=0.04,
        plausible_effect_standard_error=0.02,
        remaining_horizon=20,
        expected_reuse=1,
        freshness_weight=1,
        reversibility=1,
        downside=0,
        action_cost=0.01,
        materiality_threshold=100,
    )
    assert not zero.passes
    assert valuable.passes


def test_partial_pooling_shrinks_then_local_data_dominates() -> None:
    prior = NormalEffect(2.0, 1.0)
    weak_local = partial_pool(prior, NormalEffect(0.0, 4.0), transport_weight=1)
    strong_local = partial_pool(prior, NormalEffect(0.0, 0.01), transport_weight=1)
    assert 0 < weak_local.mean < 2
    assert abs(strong_local.mean) < abs(weak_local.mean)


def test_adversarial_transfer_has_zero_weight() -> None:
    report = transport_report(
        np.zeros(3),
        np.zeros(3),
        action_compatible=True,
        source_effect=NormalEffect(2.0, 0.01),
        target_pilot=NormalEffect(-2.0, 0.01),
        overlap=1,
        freshness=1,
    )
    assert report.support is TransportSupport.NO_TRANSPORT
    assert report.source_weight == 0


def test_unrelated_merchant_transfer_is_zero() -> None:
    report = transport_report(
        np.zeros(4),
        np.full(4, 10.0),
        action_compatible=True,
        source_effect=NormalEffect(1.0, 1.0),
        target_pilot=None,
        overlap=1,
        freshness=1,
    )
    assert report.source_weight == 0


def test_cuped_and_oof_cupac_reduce_variance_without_effect_bias() -> None:
    rng = np.random.default_rng(10)
    x = rng.normal(size=(1200, 3))
    treatment = rng.integers(0, 2, len(x))
    historical = 4 * x[:, 0] + rng.normal(0, 0.5, len(x))
    outcome = historical + 1.5 * treatment + rng.normal(0, 1, len(x))
    cuped, cuped_report = cuped_adjust(outcome, historical)
    cupac, predictions, report = cupac_adjust_oof(
        outcome,
        x,
        historical,
        feature_names=("rfm", "aov", "pre_margin"),
        forbidden_post_treatment_features=frozenset({"purchase_after"}),
    )
    raw_effect = outcome[treatment == 1].mean() - outcome[treatment == 0].mean()
    adjusted_effect = cupac[treatment == 1].mean() - cupac[treatment == 0].mean()
    assert cuped_report.variance_reduction > 0.5
    assert report.oof and report.variance_reduction > 0.5
    assert np.std(predictions) > 0
    assert abs(raw_effect - adjusted_effect) < 0.25
    assert np.var(cuped) < np.var(outcome)


def test_cupac_rejects_post_treatment_features() -> None:
    with pytest.raises(ValueError, match="post-treatment"):
        cupac_adjust_oof(
            np.ones(20),
            np.ones((20, 1)),
            np.ones(20),
            feature_names=("purchase_after",),
            forbidden_post_treatment_features=frozenset({"purchase_after"}),
        )


def test_experiment_optimizer_rejects_zero_value_and_selects_high_value() -> None:
    common = dict(
        future_population=50_000,
        relevance=0.8,
        outcome_standard_deviation=2.0,
        direct_cost_per_unit=0.2,
        sample_sizes=(100, 300),
        allocations=(0.4, 0.5, 0.6),
        enrollments=(EnrollmentStrategy.RANDOM, EnrollmentStrategy.STRATIFIED),
        seed=22,
    )
    zero = optimize_experiment(NormalActionEvidence(-2.0, 0.0), **common)
    high = optimize_experiment(NormalActionEvidence(0.0, 1.0), **common)
    assert not zero.test_allowed
    assert high.test_allowed
    assert high.sample_size in (100, 300)
    assert high.treatment_allocation in (0.4, 0.5, 0.6)


def test_propensity_logging_and_support_floor() -> None:
    action, propensity = logged_assignment(np.array([0.1, 0.8]), treatment_allocation=0.4)
    assert action.tolist() == [1, 0]
    assert propensity.tolist() == [0.4, 0.6]
    with pytest.raises(ValueError, match="support floor"):
        logged_assignment(np.array([0.5]), treatment_allocation=0.99)
    assert 0.1 <= neyman_allocation(10, 1) <= 0.9


def test_progressive_g0_to_g1_and_g1_to_g2_require_incremental_value() -> None:
    positive = np.full(400, 1.0)
    g1 = evaluate_complexity_promotion(
        positive,
        from_level=PolicyGranularity.G0_GLOBAL,
        to_level=PolicyGranularity.G1_SEGMENT,
        effective_sample_size=400,
        minimum_effective_sample_size=200,
        heterogeneity_supported=True,
        stable=True,
        economic_materiality=0.1,
    )
    g2 = evaluate_complexity_promotion(
        positive,
        from_level=PolicyGranularity.G1_SEGMENT,
        to_level=PolicyGranularity.G2_INDIVIDUAL,
        effective_sample_size=400,
        minimum_effective_sample_size=300,
        heterogeneity_supported=True,
        stable=True,
        economic_materiality=0.1,
    )
    assert g1.promoted and g2.promoted


def test_homogeneous_fixture_rejects_false_personalization() -> None:
    report = evaluate_complexity_promotion(
        np.full(500, 1.0),
        from_level=PolicyGranularity.G0_GLOBAL,
        to_level=PolicyGranularity.G1_SEGMENT,
        effective_sample_size=500,
        minimum_effective_sample_size=200,
        heterogeneity_supported=False,
        stable=True,
        economic_materiality=0.1,
    )
    assert not report.promoted


def test_variance_adaptive_anytime_null_harmful_profitable() -> None:
    rng = np.random.default_rng(99)
    null = empirical_bernstein_confidence_sequence(
        np.clip(rng.normal(0, 1, 3000), -3, 3), lower_bound=-3, upper_bound=3
    )
    harmful = empirical_bernstein_confidence_sequence(
        np.clip(rng.normal(-0.3, 1, 3000), -3, 3), lower_bound=-3, upper_bound=3
    )
    profitable = empirical_bernstein_confidence_sequence(
        np.clip(rng.normal(0.6, 1, 3000), -3, 3), lower_bound=-3, upper_bound=3
    )
    assert null.promoted_at is None
    assert harmful.promoted_at is None
    assert profitable.promoted_at is not None
