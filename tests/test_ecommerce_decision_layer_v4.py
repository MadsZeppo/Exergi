import numpy as np

from benchmarks.customer_twin_decision_lab_v2.lab import initial_population
from benchmarks.ecommerce_decision_layer_v4.decision import features, simulate
from benchmarks.ecommerce_decision_layer_v4.targeting import validate_targeting


def test_features_exclude_latent_customer_traits() -> None:
    p = initial_population(1, 20)
    x = features(p, np.full(20, 0.4), np.zeros(20), np.full(20, 365.0), full=True)
    before = x.copy()
    p.price_sensitivity[:] = 1
    p.shipping_sensitivity[:] = 1
    p.fatigue[:] = 1
    assert np.array_equal(
        before, features(p, np.full(20, 0.4), np.zeros(20), np.full(20, 365.0), full=True)
    )


def test_simulator_is_deterministic_under_common_seed() -> None:
    left, _ = simulate("null", 7, 300, 5, "v4_learning")
    right, _ = simulate("null", 7, 300, 5, "v4_learning")
    assert left == right


def test_null_does_not_false_act_after_test_phase() -> None:
    rows, _ = simulate("null", 8, 500, 8, "v4_learning")
    assert sum(int(row["false_act"]) for row in rows) == 0


def test_heldout_targeting_reports_all_depths_and_actions() -> None:
    rows = validate_targeting("heterogeneous_response", 9, 1200)
    assert {float(row["top_fraction"]) for row in rows} == {0.05, 0.1, 0.2, 0.5, 1.0}
    assert {row["action"] for row in rows} == {"free_shipping", "discount"}
