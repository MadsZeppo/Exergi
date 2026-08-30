from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.dgp import (
    decision_batch,
    generate_customer_pool,
)
from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.evaluator_only import (
    potential_outcomes,
    randomized_log,
)
from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.observed import (
    ACTION_INDEX,
    FORBIDDEN_POLICY_KEYS,
    reject_forbidden_payload,
    state_hash,
)


def test_v14_customer_pool_is_unique_deterministic_and_oracle_free() -> None:
    first = generate_customer_pool("V14_M01")
    second = generate_customer_pool("V14_M01")
    assert len(first.customer_ids) == len(set(first.customer_ids.tolist())) == 20_000
    assert np.array_equal(first.customer_ids, second.customer_ids)
    assert np.array_equal(first.features, second.features)
    assert not FORBIDDEN_POLICY_KEYS & set(first.feature_names)


def test_v14_observed_batch_is_point_in_time_deterministic_and_serializable() -> None:
    pool = generate_customer_pool("V14_M02")
    first = decision_batch(pool, 7)
    second = decision_batch(pool, 7)
    assert state_hash(first) == state_hash(second)
    assert first.policy_payload()["week"] == 7
    assert not FORBIDDEN_POLICY_KEYS & set(first.policy_payload())


def test_v14_oracle_payload_is_mechanically_rejected_by_policy_boundary() -> None:
    pool = generate_customer_pool("V14_M01")
    oracle = potential_outcomes(decision_batch(pool, 3, batch_size=20))
    with pytest.raises(ValueError, match="evaluator-only"):
        reject_forbidden_payload(dataclasses.asdict(oracle))


def test_v14_contribution_profit_identity_and_suppression_semantics() -> None:
    pool = generate_customer_pool("V14_M03")
    batch = decision_batch(pool, 3, batch_size=30)
    oracle = potential_outcomes(batch)
    row = 0
    action = ACTION_INDEX["EMAIL_REMINDER"]
    expected = (
        oracle.potential_gross_revenue[row, action]
        - oracle.potential_discounts[row, action]
        - oracle.potential_refunds[row, action]
        + oracle.potential_shipping_revenue[row, action]
        - oracle.potential_cogs[row, action]
        - oracle.potential_payment_fees[row, action]
        - oracle.potential_shipping_cost[row, action]
        - oracle.potential_shipping_subsidy[row, action]
        - oracle.potential_fulfilment_cost[row, action]
        - oracle.potential_return_shipping_cost[row, action]
        - oracle.potential_restocking_loss[row, action]
        - oracle.potential_channel_cost[row, action]
        - oracle.potential_switching_cost[row, action]
    )
    assert oracle.potential_contribution_profit[row, action] == pytest.approx(expected)
    assert np.array_equal(
        oracle.potential_contribution_profit[:, ACTION_INDEX["SUPPRESS_DO_NOT_CONTACT"]],
        oracle.potential_contribution_profit[:, ACTION_INDEX["BAU_NO_ACTION"]],
    )


def test_v14_randomized_log_has_known_propensity_and_only_observed_action() -> None:
    pool = generate_customer_pool("V14_M04")
    batch = decision_batch(pool, 5, batch_size=50)
    logged, oracle = randomized_log(batch)
    rows = np.arange(len(logged.assignment))
    assert np.isfinite(logged.logged_propensity).all()
    assert (logged.logged_propensity > 0).all()
    assert np.array_equal(
        logged.contribution_profit,
        oracle.potential_contribution_profit[rows, logged.assignment],
    )


def test_v14_missing_costs_and_corrupt_propensity_fail_closed_inputs() -> None:
    pool = generate_customer_pool("V14_M01")
    incomplete = decision_batch(pool, 23, batch_size=20)
    assert incomplete.world_family == "INCOMPLETE_COSTS"
    assert not incomplete.cost_complete[:, 1:-1].any()
    corrupted = decision_batch(pool, 31, batch_size=20)
    assert corrupted.world_family == "DATA_CORRUPTION"
    logged, _ = randomized_log(corrupted)
    assert np.isnan(logged.logged_propensity).all()
