from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np

from benchmarks.customer_twin_decision_lab_v2.lab import (
    initial_population,
    simulate_policy,
    true_logit_effect,
)
from commercial_twin.merchant_validation.contracts import EvidenceLabel, MerchantLearningRecord
from commercial_twin.merchant_validation.learning import (
    HistoricalEvidenceMatcher,
    HistoricalSupport,
    LearnedRecommendation,
)

NOW = datetime(2027, 1, 1, tzinfo=UTC)
STATE = {"lifecycle": "established", "value_band": "high", "intent_band": "high"}


def record(effect: float, se: float, sample: int, *, age_days: int = 0) -> MerchantLearningRecord:
    return MerchantLearningRecord(
        merchant_id=uuid4(),
        experiment_id=uuid4(),
        pre_action_state=STATE,
        action_definition={"action_type": "free_shipping"},
        outcome_definition={"primary": "contribution_profit"},
        estimated_effect={"per_customer": effect, "sample_size": sample},
        uncertainty={"se": se},
        economics={"identified": True},
        evidence=EvidenceLabel.SIMULATED_ONLY,
        recorded_at=NOW - timedelta(days=age_days),
    )


def test_support_and_recommendation_states() -> None:
    matcher = HistoricalEvidenceMatcher(min_high_support=100, stale_after_days=60)
    missing = matcher.match(
        [], state=STATE, action_type="free_shipping", as_of=NOW, full_state=True
    )
    assert (missing.support, missing.recommendation) == (
        HistoricalSupport.OUT_OF_SUPPORT,
        LearnedRecommendation.TEST,
    )
    partial = matcher.match(
        [record(1, 0.2, 40)], state=STATE, action_type="free_shipping", as_of=NOW, full_state=True
    )
    assert partial.support is HistoricalSupport.PARTIAL_SUPPORT
    assert partial.recommendation is LearnedRecommendation.TEST
    positive = matcher.match(
        [record(1, 0.1, 200)], state=STATE, action_type="free_shipping", as_of=NOW, full_state=True
    )
    assert positive.recommendation is LearnedRecommendation.ACT
    negative = matcher.match(
        [record(-1, 0.1, 200)], state=STATE, action_type="free_shipping", as_of=NOW, full_state=True
    )
    assert negative.recommendation is LearnedRecommendation.AVOID
    stale = matcher.match(
        [record(1, 0.1, 200, age_days=90)],
        state=STATE,
        action_type="free_shipping",
        as_of=NOW,
        full_state=True,
    )
    assert (stale.support, stale.recommendation) == (
        HistoricalSupport.STALE,
        LearnedRecommendation.VERIFY,
    )


def test_individual_population_has_hidden_persistent_traits() -> None:
    population = initial_population(12, 500)
    assert len(population.intent) == 500
    assert np.std(population.loyalty) > 0
    assert np.std(population.price_sensitivity) > 0
    before = population.intent.copy()
    simulate_policy("null", 12, 500, 2, "control")
    assert np.array_equal(
        population.intent, before
    )  # simulation clones its own deterministic state


def test_world_action_effects_are_heterogeneous() -> None:
    population = initial_population(18, 600)
    shipping, discount = true_logit_effect("heterogeneous_response", 2, population)
    assert len(np.unique(shipping)) > 2
    assert np.any(shipping == 0)
    assert np.any(discount == 0)


def test_learning_changes_policy_trajectory() -> None:
    frozen, _ = simulate_policy("free_shipping_winner", 44, 1200, 8, "frozen_twin")
    learning, records = simulate_policy("free_shipping_winner", 44, 1200, 8, "learning_twin")
    assert records
    assert [row["treated"] for row in frozen] != [row["treated"] for row in learning]


def test_deterministic_common_initial_world() -> None:
    first, _ = simulate_policy("temporal_drift", 77, 800, 4, "control")
    second, _ = simulate_policy("temporal_drift", 77, 800, 4, "control")
    assert first == second
