from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import pytest

from benchmarks.ecommerce_decision_layer_v7_1.evaluation import evaluate_candidate
from benchmarks.ecommerce_decision_layer_v7_1.models import candidate_models
from benchmarks.ecommerce_decision_layer_v7_1.packs import v71_pack_specs, write_pack_manifest
from benchmarks.ecommerce_decision_layer_v7_1.sequential_assurance import (
    FAMILY_BUDGET,
    MERCHANT_BUDGET,
    SCENARIOS,
    observable_lifecycle_decision,
    run_path,
)
from benchmarks.ecommerce_decision_layer_v7_1.world import (
    V71ObservedWorld,
    V71WorldFamily,
    generate_v71_world,
)


def _spec(pack: str, family: V71WorldFamily):
    return next(spec for spec in v71_pack_specs(pack) if spec.family is family)


def test_v71_pack_dimensions_are_disjoint() -> None:
    specs = [spec for pack in "OPQRSTU" for spec in v71_pack_specs(pack)]
    assert len({spec.seed for spec in specs}) == len(specs)
    assert len({spec.merchant_id for spec in specs}) == len(specs)
    assert len({spec.world_id for spec in specs}) == len(specs)


def test_pack_u_cannot_be_materialized(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="Pack U is sealed"):
        write_pack_manifest("U", tmp_path)


def test_observed_contract_has_no_oracle_effect() -> None:
    names = {field.name for field in fields(V71ObservedWorld)}
    assert "individual_net_effect" not in names
    assert not any("oracle" in name or "truth" in name for name in names)


def test_v71_costs_are_explicit_and_reduce_net_effect() -> None:
    spec = _spec("O", V71WorldFamily.HOMOGENEOUS_POSITIVE)
    _, oracle = generate_v71_world(spec)
    assert spec.treatment_cost > 0
    assert spec.switching_cost > 0
    assert np.mean(oracle.individual_net_effect) < 1.25 * 1.08


def test_all_development_candidates_fit_and_predict_finite_effects() -> None:
    spec = replace(
        _spec("O", V71WorldFamily.MATERIAL_OBSERVABLE_LINEAR), observations=1_000
    )
    observed, _ = generate_v71_world(spec)
    for model in candidate_models(spec.seed):
        model.fit(
            observed.features,
            observed.assignment,
            observed.contribution_profit,
            observed.logged_propensity,
        )
        prediction = model.effect(observed.features[:100])
        assert prediction.shape == (100,)
        assert np.all(np.isfinite(prediction))


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        (
            V71WorldFamily.MATERIAL_OBSERVABLE_LINEAR,
            "MATERIAL_OBSERVABLE_PERSONALIZATION",
        ),
        (V71WorldFamily.NONMATERIAL_SPARSE, "NONMATERIAL_PERSONALIZATION"),
        (
            V71WorldFamily.UNOBSERVABLE_HETEROGENEITY,
            "MATERIAL_UNOBSERVABLE_PERSONALIZATION",
        ),
        (V71WorldFamily.INSUFFICIENT_SUPPORT, "UNSUPPORTED_PERSONALIZATION"),
    ],
)
def test_evaluator_classifies_economic_identifiability(
    family: V71WorldFamily, expected: str
) -> None:
    spec = _spec("O", family)
    model = next(model for model in candidate_models(spec.seed) if model.name == "forest_t_learner")
    result = evaluate_candidate(spec, model)
    assert result.oracle_taxonomy == expected
    assert not result.unsupported_act


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_sequential_path_never_exceeds_declared_budgets(scenario: str) -> None:
    for seed in range(3):
        result = run_path(scenario, 900_000 + seed)
        assert not result.hard_budget_breach
        assert not result.family_budget_breach
        assert not result.exposure_over_available_risk
        assert result.maximum_drawdown <= MERCHANT_BUDGET
        assert 0 <= result.maximum_risk_utilization <= 1
        assert FAMILY_BUDGET <= MERCHANT_BUDGET


def test_lifecycle_uses_only_observable_history_and_fails_closed_on_support() -> None:
    history = [0.4, 0.5, 0.6, 0.7]
    first = observable_lifecycle_decision(
        "TEST", history, support_valid=True, assignment_integrity_valid=True
    )
    second = observable_lifecycle_decision(
        "TEST", list(history), support_valid=True, assignment_integrity_valid=True
    )
    assert first == second
    assert first[0] == "ACTIVE"
    unsupported = observable_lifecycle_decision(
        "ACTIVE", history, support_valid=False, assignment_integrity_valid=True
    )
    assert unsupported == ("PAUSED", "INSUFFICIENT_SUPPORT")
    assert observable_lifecycle_decision(
        "TEST", [0.0, 0.0, 0.0, 0.0], support_valid=True, assignment_integrity_valid=True
    )[0] != "ACTIVE"
    assert observable_lifecycle_decision(
        "TEST", [-0.4, -0.5, -0.6], support_valid=True, assignment_integrity_valid=True
    )[0] != "ACTIVE"


def test_insufficient_support_never_assigns_or_activates() -> None:
    result = run_path("INSUFFICIENT_SUPPORT", 991_001)
    assert result.assignments == 0
    assert result.active_periods == 0
