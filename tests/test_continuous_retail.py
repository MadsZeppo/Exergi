import numpy as np
import pytest

from decision_engine.benchmark.continuous_retail import partial_pool
from decision_engine.causal.continuous import ContinuousOutcomeRegression
from decision_engine.decision.continuous_engine import ContinuousDecisionEngine
from decision_engine.decision.continuous_support import continuous_dose_support
from decision_engine.metrics.continuous import (
    dose_response_metrics,
    optimal_discount_metrics,
    spillover_recovery_metrics,
)
from decision_engine.synthetic.retail.world import (
    RetailWorldConfig,
    generate_retail_world,
)


def small_world(**kwargs):
    return generate_retail_world(
        RetailWorldConfig(stores=1, categories=2, skus=4, days=30, **kwargs)
    )


def test_continuous_response_is_bounded_and_reproducible() -> None:
    first, second = small_world(seed=7), small_world(seed=7)
    assert first.frame.equals(second.frame)
    assert first.frame["discount"].min() >= 0
    assert first.frame["discount"].max() <= 0.30
    response = first.expected_demand(np.array([0]), np.array([0.0, 0.1, 0.2]))
    assert response.shape == (1, 3)
    assert np.all(response > 0)


def test_observational_assignment_is_confounded() -> None:
    world = small_world(seed=2)
    discount = world.frame["discount"].to_numpy()
    inventory_excess = world.frame["inventory"].to_numpy() / np.maximum(world.baseline_demand, 0.01)
    assert np.corrcoef(discount, inventory_excess)[0, 1] > 0.02


def test_post_treatment_mediator_is_blocked() -> None:
    world = small_world(seed=1)
    with pytest.raises(ValueError, match="post-treatment"):
        ContinuousOutcomeRegression().fit(
            world.frame,
            ["regular_price", "website_traffic_after_promo"],
        )


def test_support_detects_unobserved_dose_and_grows_uncertainty() -> None:
    doses = np.linspace(0, 0.1, 100)
    supported = continuous_dose_support(doses, 0.05, minimum_comparables=10)
    unsupported = continuous_dose_support(doses, 0.30)
    assert supported.status == "STRONG_SUPPORT"
    assert unsupported.status == "OUT_OF_SUPPORT"
    assert unsupported.uncertainty_multiplier > supported.uncertainty_multiplier


def test_truth_profit_optimizer_and_regret() -> None:
    doses = np.array([0.0, 0.1, 0.2])
    truth = np.array([[1.0, 3.0, 2.0], [4.0, 2.0, 1.0]])
    estimate = np.array([[1.0, 2.0, 3.0], [4.0, 2.0, 1.0]])
    result = optimal_discount_metrics(truth, estimate, doses)
    assert result["optimal_discount_mae"] == pytest.approx(0.05)
    assert result["economic_regret"] == pytest.approx(0.5)


def test_dose_response_integration_metrics() -> None:
    doses = np.array([0.0, 0.5, 1.0])
    truth = np.zeros((1, 3))
    estimate = np.ones((1, 3))
    metrics = dose_response_metrics(truth, estimate, doses)
    assert metrics["rmse"] == 1
    assert metrics["integrated_absolute_error"] == 1
    assert metrics["integrated_squared_error"] == 1


def test_stockout_censors_observed_demand() -> None:
    world = small_world(seed=5)
    rows, doses = np.arange(world.frame.height), np.array([0.3])
    latent = world.expected_demand(rows, doses)[:, 0]
    observed = world.observed_demand(rows, doses)[:, 0]
    assert np.all(observed <= latent)
    assert np.any(observed < latent)


def test_pull_forward_can_reduce_long_horizon_value() -> None:
    world = small_world(seed=4, pull_forward=2.0)
    kernel = world.dynamic_multiplier(0.2)
    assert kernel[:7].sum() > 0
    assert kernel[:28].sum() < kernel[:7].sum()


def test_cannibalization_and_halo_have_opposite_signs() -> None:
    world = generate_retail_world(
        RetailWorldConfig(stores=1, categories=2, skus=6, days=30, seed=3, cannibalization=0.2)
    )
    edges = world.interaction_matrix[world.interaction_matrix != 0]
    assert np.any(edges < 0)
    assert np.any(edges > 0)
    assert abs(edges.min()) > edges.max()


def test_spillover_metrics_known_perfect_recovery() -> None:
    truth = np.array([[0.0, -1.0, 0.5], [-0.2, 0.0, 0.0], [0.1, 0.0, 0.0]])
    metrics = spillover_recovery_metrics(truth, truth, top_k=3)
    assert metrics["sign_accuracy"] == 1
    assert metrics["magnitude_mae"] == 0
    assert metrics["top_k_precision"] == 1


def test_engine_abstains_beyond_observed_support() -> None:
    world = small_world(seed=9, support="bad")
    cutoff = int(world.frame.height * 0.7)
    estimator = ContinuousOutcomeRegression(kind="elasticity").fit(
        world.frame[:cutoff], ["regular_price", "inventory", "weekday"]
    )
    engine = ContinuousDecisionEngine(estimator)
    engine.history_ = world.frame[:cutoff]
    recommendation = engine.recommend(world.frame[cutoff : cutoff + 10], np.array([0.25, 0.30]))
    assert recommendation.status == "ABSTAIN"
    assert recommendation.dose is None


def test_profit_curve_uses_unit_cost() -> None:
    world = small_world(seed=6)
    row = np.array([0])
    demand = world.observed_demand(row, np.array([0.0]))[0, 0]
    expected = (world.frame[0, "regular_price"] - world.frame[0, "unit_cost"]) * demand
    assert world.profit_curve(row, np.array([0.0]))[0, 0] == pytest.approx(expected)


def test_partial_pooling_improves_sparse_controlled_fixture() -> None:
    truth = np.array([2.0, 2.0, 2.0, 2.0])
    noisy = np.array([2.1, 1.9, 5.0, -1.0])
    groups = np.array([0, 0, 0, 0])
    counts = np.array([100, 100, 2, 2])
    pooled = partial_pool(noisy, groups, counts, strength=20)
    assert np.mean((pooled - truth) ** 2) < np.mean((noisy - truth) ** 2)
