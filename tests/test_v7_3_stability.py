from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from decision_engine.stability_v73 import (
    CANDIDATE_GATES,
    GateInput,
    WorldFamily,
    assess_candidates,
    compute_evidence,
    generate_world,
)


def _randomized(effect: float, *, supported: bool = True, seed: int = 81) -> GateInput:
    rng = np.random.default_rng(seed)
    n = 4_000
    treatment = rng.integers(0, 2, n, dtype=np.int64)
    features = rng.normal(size=(n, 3))
    outcome = 2.0 + 0.2 * features[:, 0] + effect * treatment + rng.normal(0, 0.5, n)
    return GateInput(
        outcome=outcome,
        treatment=treatment,
        features=features,
        unit_id=np.asarray([f"u-{index}" for index in range(n)]),
        split_key=rng.integers(0, np.iinfo(np.uint64).max, n, dtype=np.uint64),
        logged_propensity=np.full(n, 0.5),
        mature=np.ones(n, dtype=bool),
        action_cost=0.05,
        per_unit_budget=0.25,
        support_valid=supported,
    )


def test_gate_contract_contains_no_oracle_or_truth_field() -> None:
    assert not any(
        "truth" in name or "oracle" in name
        for name in inspect.signature(compute_evidence).parameters
    )
    assert not any("truth" in name or "oracle" in name for name in GateInput.__annotations__)


def test_all_candidates_fail_closed_without_support() -> None:
    evidence = compute_evidence(_randomized(1.0, supported=False), seed=72, bootstrap_replicates=50)
    decisions = assess_candidates(evidence)
    assert set(decisions) == set(CANDIDATE_GATES)
    assert not any(decision.act for decision in decisions.values())
    assert all(not decision.supported for decision in decisions.values())


def test_positive_randomized_effect_acts_and_harmful_effect_abstains() -> None:
    positive = assess_candidates(
        compute_evidence(_randomized(0.8), seed=73, bootstrap_replicates=100)
    )
    harmful = assess_candidates(
        compute_evidence(_randomized(-0.8), seed=74, bootstrap_replicates=100)
    )
    assert positive["combined_economic"].act
    assert positive["cross_fitted_aipw_lcb"].act
    assert not any(decision.act for decision in harmful.values())


def test_gate_is_deterministic_for_seed() -> None:
    data = _randomized(0.4)
    first = compute_evidence(data, seed=99, bootstrap_replicates=50)
    second = compute_evidence(data, seed=99, bootstrap_replicates=50)
    assert first == second
    assert assess_candidates(first) == assess_candidates(second)


def test_dgp_truth_is_mechanically_separate_and_seed_levels_differ() -> None:
    development = generate_world(WorldFamily.NULL, 7_303_001, 4)
    validation = generate_world(WorldFamily.NULL, 7_303_002, 4)
    assert development.evaluator_truth.true_net_value == 0.0
    assert validation.evaluator_truth.true_net_value == 0.0
    assert not np.array_equal(development.gate_input.split_key, validation.gate_input.split_key)
    assert not hasattr(development.gate_input, "true_net_value")


@pytest.mark.parametrize(
    "family",
    [
        WorldFamily.NULL,
        WorldFamily.HARMFUL,
        WorldFamily.MATERIAL_POSITIVE,
        WorldFamily.NEGATIVE_MARGIN,
        WorldFamily.INTEGRITY_FAILURE,
    ],
)
def test_dgp_generates_finite_observable_mature_outcomes(family: WorldFamily) -> None:
    world = generate_world(family, 7_303_001, 11)
    data = world.gate_input
    assert np.all(np.isfinite(data.outcome[data.mature]))
    assert 0.0 <= float(np.mean(data.outcome[data.mature] == 0)) <= 1.0
    assert len(np.unique(data.unit_id)) == len(data.unit_id)


def test_preregistration_has_500_worlds_per_family_and_disjoint_roots() -> None:
    config = json.loads(
        Path(
            "benchmarks/ecommerce_decision_layer_v7_3/manifests/gate_benchmark_preregistration.json"
        ).read_text()
    )
    levels = config["levels"]
    assert all(level["worlds_per_family"] >= 500 for level in levels.values())
    assert len({level["seed_root"] for level in levels.values()}) == 3
    assert config["hillstrom_status"] == "DEVELOPMENT_CONSUMED"


def test_power_population_excludes_worlds_where_act_is_forbidden() -> None:
    source = Path("benchmarks/ecommerce_decision_layer_v7_3/stability_benchmark.py").read_text()
    assert 'row["materially_positive"]' in source
    assert 'row["supported_action"]' in source
    assert 'row["budget_valid"]' in source
    assert 'row["early_release_safe"]' in source


def test_runner_has_no_real_validation_or_sealed_outcome_path() -> None:
    source = Path("benchmarks/ecommerce_decision_layer_v7_3/stability_benchmark.py").read_text()
    assert "data/processed/hillstrom/v7_2/validation" not in source
    assert "data/processed/hillstrom/v7_2/sealed" not in source
    assert "data/processed/buy_baits/v7_2/validation" not in source
    assert "data/processed/buy_baits/v7_2/sealed" not in source


def test_duplicate_randomization_units_are_rejected() -> None:
    data = _randomized(0.2)
    with pytest.raises(ValueError, match="unique"):
        GateInput(
            **{
                **data.__dict__,
                "unit_id": np.asarray(["duplicate"] * len(data.unit_id)),
            }
        )


def test_final_development_stop_does_not_open_any_later_level() -> None:
    result = json.loads(
        Path("benchmarks/ecommerce_decision_layer_v7_3/results/v7_3_result.json").read_text()
    )
    assert result["status"] == "V7_3_GATE_FAILED_HILLSTROM_NOT_REASSESSED"
    assert result["development"]["selected_gate"] is None
    assert result["validation"] is None
    assert result["sealed_gate_test"] is None
    assert result["freeze"] is None
    assert result["hillstrom_validation_opened"] is False
    assert result["hillstrom_reassessed"] is False
    assert result["buy_baits_negative_control_run"] is False
    assert not Path(
        "benchmarks/ecommerce_decision_layer_v7_3/manifests/V7_3_GATE_FREEZE.json"
    ).exists()


def test_hillstrom_fold_forensics_preserves_existing_veto_without_reassessment() -> None:
    audit = json.loads(
        Path(
            "benchmarks/ecommerce_decision_layer_v7_3/results/hillstrom_v72_fold_forensics.json"
        ).read_text()
    )
    assert audit["status"] == "DIAGNOSTIC_ONLY_NO_GATE_CHANGE"
    assert audit["hillstrom_status"] == "DEVELOPMENT_CONSUMED"
    assert audit["validation_opened"] is False
    assert audit["sealed_test_used"] is False
    assert audit["observed_positive_fold_count"] == 4
    assert audit["observed_minimum_fold_net"] == pytest.approx(-0.16027432545201664)
    assert audit["observed_all_leave_one_out_positive"] is True
    assert audit["gate_pass"] is False


def test_no_candidate_passed_joint_development_contract() -> None:
    result = json.loads(
        Path(
            "benchmarks/ecommerce_decision_layer_v7_3/results/gate_development_summary.json"
        ).read_text()
    )
    assert result["total_worlds"] == 5_000
    assert result["eligible_gates"] == []
    assert result["selected_gate"] is None
    metrics = result["metrics"]
    assert metrics["existing_v72_fold_veto"]["false_negative_rate"] == pytest.approx(
        0.9, abs=0.001
    )
    assert metrics["bootstrap_positive_probability"]["harmful_act_rate"] > 0.01
    assert metrics["median_of_means"]["null_act_rate"] > 0.05
