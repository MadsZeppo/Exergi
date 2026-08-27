from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from benchmarks.ecommerce_decision_layer_v7.datasets.baur_adapter import (
    load_baur_profit_uplift,
)
from benchmarks.ecommerce_decision_layer_v7.datasets.registry import DatasetRegistry
from benchmarks.ecommerce_decision_layer_v7.evaluation import evaluate_world
from benchmarks.ecommerce_decision_layer_v7.packs import pack_specs, write_manifest
from benchmarks.ecommerce_decision_layer_v7.world import WorldFamily, WorldSpec, generate_world
from commercial_twin.merchant_validation.economics_contract import MerchantEconomicOutcome
from commercial_twin.merchant_validation.rct_protocol import (
    CommercialEvidenceGate,
    MerchantRCTProtocol,
)
from commercial_twin.merchant_validation.shadow_policy import ShadowDecision, ShadowPolicy
from decision_engine.core.authority import ClaimAuthority
from decision_engine.decision.action_viability import (
    ActionViabilityConfig,
    ActionViabilityEngine,
    RandomizedEconomicEvidence,
    ViabilityStatus,
)
from decision_engine.decision.heterogeneity import HeterogeneityEvidence, HeterogeneityGate
from decision_engine.decision.segment_policy import SegmentDefinition, SegmentPolicyEngine
from decision_engine.experiments.value_of_information_allocator import (
    ExperimentOption,
    ValueOfInformationAllocator,
)
from decision_engine.safety.committed_risk_ledger import (
    CommittedRiskLedger,
    ReservationStatus,
    RiskBudget,
    RiskReservationRequest,
)
from decision_engine.safety.lifecycle_controller_v7 import (
    LifecycleControllerV7,
    LifecycleInput,
    LifecycleStateV7,
)

REPOSITORY = Path(__file__).resolve().parents[1]


def _evidence(effect: float, seed: int = 91) -> RandomizedEconomicEvidence:
    rng = np.random.default_rng(seed)
    n = 800
    x = rng.normal(size=(n, 3))
    a = rng.random(n) < 0.5
    y = 4 + x[:, 0] + effect * a + rng.normal(0, 1, n)
    return RandomizedEconomicEvidence(
        y,
        a,
        np.full(n, 0.5),
        x,
        np.arange(n) // 10,
        ("rfm", "intent", "tenure"),
        ClaimAuthority.SYNTHETIC_ECONOMIC,
        "SIMULATED_RANDOMIZED",
        True,
    )


def _risk_request(identifier: str, units: int = 10) -> RiskReservationRequest:
    return RiskReservationRequest(
        identifier,
        "merchant",
        "winback",
        "message",
        "experiment",
        units,
        1.0,
        1.5,
        1.2,
        1.1,
        1,
        4,
        6,
    )


def _outcome(**overrides: object) -> MerchantEconomicOutcome:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values: dict[str, object] = {
        "experiment_id": uuid4(),
        "merchant_id": uuid4(),
        "customer_id": uuid4(),
        "interference_key": "household-1",
        "assignment_timestamp": now,
        "eligibility_snapshot_timestamp": now - timedelta(minutes=1),
        "outcome_maturity_timestamp": now + timedelta(days=30),
        "arm": "MESSAGE_ONLY",
        "propensity": 0.5,
        "delivered": True,
        "exposed": True,
        "complied": True,
        "order_revenue": 100.0,
        "item_level_cogs": 40.0,
        "merchant_funded_discount": 5.0,
        "shipping_subsidy": 3.0,
        "returns_and_refunds": 10.0,
        "payment_transaction_fees": 2.0,
        "campaign_channel_cost": 1.0,
    }
    values.update(overrides)
    return MerchantEconomicOutcome(**values)


def test_action_viability_detects_positive_effect_deterministically() -> None:
    engine = ActionViabilityEngine(ActionViabilityConfig(seed=4))
    first = engine.evaluate(_evidence(1.0))
    second = engine.evaluate(_evidence(1.0))
    assert first.status is ViabilityStatus.VIABLE
    assert first.estimate == second.estimate


def test_action_viability_does_not_promote_null_fixture() -> None:
    report = ActionViabilityEngine(ActionViabilityConfig(seed=5)).evaluate(_evidence(0.0))
    assert report.status is not ViabilityStatus.VIABLE


def test_action_viability_rejects_exposure_feature() -> None:
    evidence = _evidence(1.0)
    invalid = RandomizedEconomicEvidence(
        evidence.outcome,
        evidence.treatment,
        evidence.propensity,
        evidence.pre_treatment_features,
        evidence.cluster,
        ("rfm", "exposure", "tenure"),
        evidence.authority,
        evidence.assignment_provenance,
        True,
    )
    with pytest.raises(ValueError, match="post-treatment"):
        ActionViabilityEngine().evaluate(invalid)


def test_unknown_assignment_or_missing_cost_fails_closed() -> None:
    evidence = _evidence(1.0)
    invalid = RandomizedEconomicEvidence(
        evidence.outcome,
        evidence.treatment,
        evidence.propensity,
        evidence.pre_treatment_features,
        evidence.cluster,
        evidence.feature_names,
        ClaimAuthority.OBSERVATIONAL_ASSOCIATION,
        "UNKNOWN_ASSIGNMENT",
        False,
    )
    assert ActionViabilityEngine().evaluate(invalid).status is ViabilityStatus.INSUFFICIENT


def test_segment_policy_falls_back_to_bau_without_lower_bound() -> None:
    decision = SegmentPolicyEngine(minimum_segment_n=10).select(
        np.zeros(100),
        np.arange(100) // 5,
        (SegmentDefinition("RFM", np.arange(100) < 50),),
    )
    assert decision.fallback_to_bau


def test_heterogeneity_gate_requires_all_decomposed_checks() -> None:
    evidence = HeterogeneityEvidence(
        True,
        0.4,
        0.01,
        0.001,
        (1.0, 1.0, 1.0, 1.0, 1.0),
        np.full(500, 1.0),
        np.arange(500) // 5,
        500,
        True,
        2,
    )
    decision = HeterogeneityGate().evaluate(evidence, best_static_policy="BAU")
    assert decision.personalization_supported
    failed = HeterogeneityEvidence(**{**evidence.__dict__, "out_of_fold": False})
    failed_decision = HeterogeneityGate().evaluate(failed, best_static_policy="BAU")
    assert not failed_decision.personalization_supported


def test_voi_is_finite_horizon_and_can_refuse() -> None:
    option = ExperimentOption("family", "action", 0, 0.1, 2, 100, 0.5, 10, 1, 1, 5, 500, 50)
    decision = ValueOfInformationAllocator(seed=1).evaluate(
        option, current_best_incremental_value=0
    )
    assert not decision.test_allowed
    assert np.isfinite(decision.conservative_enbs)


def test_committed_risk_uses_max_downside_and_both_budgets() -> None:
    ledger = CommittedRiskLedger(RiskBudget(20, {"winback": 20}))
    first = ledger.reserve(_risk_request("a"))
    second = ledger.reserve(_risk_request("b"))
    assert first.downside_per_unit == 1.5
    assert first.reserved_risk == 15
    assert second.status is ReservationStatus.REJECTED
    assert ledger.snapshot().merchant_open_risk == 15


def test_risk_cannot_release_before_maturity() -> None:
    ledger = CommittedRiskLedger(RiskBudget(100, {"winback": 100}))
    ledger.reserve(_risk_request("a"))
    with pytest.raises(ValueError, match="before outcome maturity"):
        ledger.release_matured("a", current_period=3)
    ledger.release_matured("a", current_period=4)
    assert ledger.snapshot().merchant_open_risk == 0


def test_risk_invariant_over_many_requests() -> None:
    ledger = CommittedRiskLedger(RiskBudget(60, {"winback": 30}))
    for index in range(100):
        ledger.reserve(_risk_request(str(index), units=3))
        assert ledger.snapshot().merchant_open_risk <= 60
        assert ledger.snapshot().family_open_risk["winback"] <= 30


def test_lifecycle_stops_on_legitimate_harm() -> None:
    controller = LifecycleControllerV7()
    inputs = LifecycleInput(2, True, False, True, False, False, True, False, False, 10, 100, 5)
    record = controller.transition(LifecycleStateV7.ACTIVE, inputs)
    assert record.new_state is LifecycleStateV7.PAUSED
    assert record.reason_code == "OBSERVABLE_HARM_STOP"


def test_lifecycle_inputs_contain_no_oracle_fields() -> None:
    names = {field.name.lower() for field in fields(LifecycleInput)}
    assert not any("oracle" in name or "truth" in name or "change_time" in name for name in names)


def test_identical_observable_histories_give_identical_decisions() -> None:
    inputs = LifecycleInput(1, True, False, False, True, True, False, False, False, 0, 100, 4)
    first = LifecycleControllerV7().transition(LifecycleStateV7.OBSERVE, inputs)
    second = LifecycleControllerV7().transition(LifecycleStateV7.OBSERVE, inputs)
    assert (first.new_state, first.reason_code) == (second.new_state, second.reason_code)


def test_future_inputs_cannot_rewrite_earlier_ledger_record() -> None:
    controller = LifecycleControllerV7()
    start = LifecycleInput(1, True, False, False, True, True, False, False, False, 0, 100, 4)
    first = controller.transition(LifecycleStateV7.OBSERVE, start)
    harm = LifecycleInput(2, True, False, True, False, False, True, False, False, 0, 100, 4)
    controller.transition(first.new_state, harm)
    assert controller.records[0] == first
    assert controller.records[0].new_state is LifecycleStateV7.PROBE


def test_unsupported_input_has_control_fallback_from_every_state() -> None:
    controller = LifecycleControllerV7()
    unsupported = LifecycleInput(1, False, True, False, True, True, False, False, False, 999, 1, 9)
    for state in LifecycleStateV7:
        assert controller.transition(state, unsupported).new_state is LifecycleStateV7.OBSERVE


def test_evidence_expiry_removes_active_lease() -> None:
    expired = LifecycleInput(9, True, True, False, False, True, False, False, True, 500, 100, 8)
    record = LifecycleControllerV7().transition(LifecycleStateV7.ACTIVE, expired)
    assert record.new_state is LifecycleStateV7.WATCH


def test_claim_authority_only_allows_real_cp_evidence() -> None:
    allowed = [item for item in ClaimAuthority if item.permits_real_merchant_profit_claim]
    assert allowed == [ClaimAuthority.REAL_RANDOMIZED_CONTRIBUTION_PROFIT]


def test_economic_contract_is_maturity_and_cost_complete() -> None:
    outcome = _outcome()
    assert outcome.contribution_profit(observed_at=outcome.assignment_timestamp) is None
    assert outcome.contribution_profit(
        observed_at=outcome.outcome_maturity_timestamp
    ) == pytest.approx(39.0)
    incomplete = _outcome(item_level_cogs=None)
    assert incomplete.contribution_profit(observed_at=incomplete.outcome_maturity_timestamp) is None


def test_duplicated_cost_cannot_improve_profit() -> None:
    original = _outcome()
    larger_cost = _outcome(campaign_channel_cost=2.0)
    at = original.outcome_maturity_timestamp
    larger_profit = larger_cost.contribution_profit(observed_at=at)
    original_profit = original.contribution_profit(observed_at=at)
    assert larger_profit is not None and original_profit is not None
    assert larger_profit < original_profit


def test_real_protocol_requires_shadow_and_manual_approval() -> None:
    protocol = MerchantRCTProtocol(minimum_economically_relevant_effect=0.5)
    assert not protocol.launch_allowed
    assert not protocol.adaptive_allocation
    assert protocol.approximate_sample_size_per_comparison(outcome_sd=5) > 0


def test_shadow_policy_never_assigns() -> None:
    policy = ShadowPolicy()
    decision = ShadowDecision(
        merchant_id=uuid4(),
        decision_id=uuid4(),
        decided_at=datetime.now(UTC),
        action_family="winback",
        proposed_arm="MESSAGE_ONLY",
        observable_inputs={"recency": 90},
        reason_codes=("SHADOW",),
    )
    policy.record(decision)
    assert not policy.records[0].assignment_created


def test_commercial_claim_gate_is_strict() -> None:
    gate = CommercialEvidenceGate(
        preregistered_experiments=3,
        merchants=2,
        replicated_action_families=1,
        pooled_cp_lower=0.1,
        all_negative_trials_included=True,
        any_hard_budget_breach=False,
        any_merchant_serious_loss=False,
    )
    assert gate.permits_real_profit_claim
    assert not gate.model_copy(update={"any_merchant_serious_loss": True}).permits_real_profit_claim


def test_dataset_registry_enforces_criteo_itt_and_claim_boundaries() -> None:
    registry = DatasetRegistry.load(
        REPOSITORY / "benchmarks/ecommerce_decision_layer_v7/datasets/registry.yaml"
    )
    criteo = registry.get("criteo_uplift_v2")
    assert "exposure" in criteo.raw["post_treatment_variables"]
    assert "use_exposure_as_assignment" in criteo.forbidden_claims
    assert criteo.verify_file(REPOSITORY)
    assert registry.get("x5_retailhero").assignment_provenance == "UNKNOWN_ASSIGNMENT"


def test_baur_adapter_does_not_fabricate_rows() -> None:
    with pytest.raises(FileNotFoundError, match="no lawful public row-level"):
        load_baur_profit_uplift()


def test_pack_ids_and_seeds_are_disjoint_and_final_is_sealed(tmp_path: Path) -> None:
    packs = [pack_specs(pack) for pack in "HIJKLMN"]
    ids = [spec.merchant_id for pack in packs for spec in pack]
    seeds = [spec.seed for pack in packs for spec in pack]
    assert len(ids) == len(set(ids))
    assert len(seeds) == len(set(seeds))
    with pytest.raises(PermissionError, match="Final Pack N"):
        write_manifest("N", tmp_path)


def test_world_determinism_and_observable_oracle_separation() -> None:
    spec = WorldSpec("w", "m", "a", WorldFamily.QUALITATIVE_HETEROGENEITY, 123)
    first_observed, first_oracle = generate_world(spec)
    second_observed, second_oracle = generate_world(spec)
    np.testing.assert_array_equal(first_observed.outcome, second_observed.outcome)
    np.testing.assert_array_equal(first_oracle.individual_effect, second_oracle.individual_effect)
    assert not any("effect" in field.name for field in fields(type(first_observed)))


def test_propensity_corruption_and_insufficient_support_never_act() -> None:
    for family in (WorldFamily.PROPENSITY_LOGGING_ERROR, WorldFamily.INSUFFICIENT_SUPPORT):
        spec = WorldSpec("w", "m", "a", family, 100 + len(family))
        result = evaluate_world(spec, "ridge_t_learner")
        assert not result.unsupported_act
        assert result.decision != "ACT"
