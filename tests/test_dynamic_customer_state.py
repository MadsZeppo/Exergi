from __future__ import annotations

import pytest
from pydantic import ValidationError

from commercial_twin.dynamic_customer_state import (
    DynamicCustomerState,
    DynamicsBenchmarkAuthority,
    JDSearchCausalTransitionKernel,
    MerchantAction,
    Reliability,
    stable_customer_split,
)


def test_quick_mode_has_no_official_authority() -> None:
    authority = DynamicsBenchmarkAuthority(quick=True)
    with pytest.raises(PermissionError, match="Quick mode"):
        authority.require_definitive("read official-final targets")


def test_definitive_mode_has_official_authority() -> None:
    DynamicsBenchmarkAuthority(quick=False).require_definitive("freeze")


def state() -> DynamicCustomerState:
    distribution = {"CLICK": 0.25, "CART": 0.25, "FLW": 0.25, "ORD": 0.25}
    return DynamicCustomerState(
        customer_key="x",
        as_of_event=10,
        predictive_state_vector=(0.2,),
        latent_state_vector=(0.1,),
        next_event_probabilities=distribution,
        purchase_next_5_probability=0.2,
        purchase_next_10_probability=0.3,
        purchase_next_20_probability=0.4,
        cart_next_5_probability=0.3,
        cart_next_10_probability=0.4,
        cart_next_20_probability=0.5,
        expected_next_5_event_mix=distribution,
        expected_next_10_event_mix=distribution,
        expected_next_20_event_mix=distribution,
        purchase_history_depth=1,
        behavioral_history_depth=10,
        state_uncertainty=1.0,
        empirical_reliability=Reliability.MEDIUM,
        model_version="v1",
        feature_version="v1",
    )


def test_state_distributions_are_simplexes() -> None:
    invalid = {"CLICK": 0.5, "CART": 0.5, "FLW": 0.5, "ORD": 0.5}
    with pytest.raises(ValidationError, match="sum to one"):
        state().model_copy(update={"next_event_probabilities": invalid}).model_validate(
            state().model_copy(update={"next_event_probabilities": invalid})
        )


def test_customer_split_is_stable_and_allowlisted() -> None:
    assert stable_customer_split(123) == stable_customer_split(123)
    assert stable_customer_split(123) in {"TRAIN", "DEVELOPMENT", "OFFICIAL_FINAL"}


def test_customer_behavior_cannot_be_merchant_action() -> None:
    with pytest.raises(ValidationError):
        MerchantAction(action_type="CLICK", action_id="bad")


def test_jdsearch_causal_kernel_fails_closed() -> None:
    action = MerchantAction(action_type="EMAIL", action_id="email")
    result = JDSearchCausalTransitionKernel().evaluate(state(), action)
    assert result.status == "INSUFFICIENT_CAUSAL_EVIDENCE"
