from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path

import numpy as np
import pytest

from benchmarks.ecommerce_decision_layer_v7_2.sequential_assurance import run_path
from decision_engine.economic_policy_v72 import (
    ClaimAuthority,
    ClaimLevel,
    CrossFittedOutcomeModel,
    EconomicPolicyDataset,
    EconomicPolicyEngine,
    EvidenceBatch,
    FreezeManifest,
    SealedTestGuard,
    SequentialController,
    SequentialControllerConfig,
    evaluate_policy,
    model_candidates,
)
from decision_engine.economic_policy_v72.sequential import LifecycleState
from decision_engine.economic_policy_v72.splits import (
    assigned_split,
    build_split_manifest,
    stable_unit_hash,
    write_manifest_immutable,
)


def _rct(seed: int = 4, n: int = 600, arms: int = 3) -> EconomicPolicyDataset:
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(n, 3))
    action = rng.integers(0, arms, size=n, dtype=np.int64)
    gross = 2.0 + 0.3 * features[:, 0] + (action == 1) * 0.6 + (action == 2) * -0.2
    outcome = np.maximum(gross + rng.normal(0, 0.3, n), 0.0)
    propensity = np.full((n, arms), 1 / arms)
    costs = np.zeros((n, arms))
    costs[:, 1:] = 0.1
    return EconomicPolicyDataset(
        features,
        action,
        outcome,
        propensity,
        costs,
        np.ones((n, arms), dtype=bool),
        np.asarray([f"u-{index}" for index in range(n)]),
        feature_names=("x0", "x1", "x2"),
    )


def test_multi_arm_contract_rejects_duplicate_units_and_invalid_propensity() -> None:
    data = _rct()
    with pytest.raises(ValueError, match="duplicate"):
        replace(data, unit_id=np.asarray(["same"] * len(data.action)))
    bad = data.propensity.copy()
    bad[:, 0] = 0
    with pytest.raises(ValueError, match="propensities"):
        replace(data, propensity=bad)


def test_cross_fitting_covers_every_row_once_and_is_deterministic() -> None:
    data = _rct()
    first = CrossFittedOutcomeModel(model_candidates()[0], folds=4, seed=99)
    second = CrossFittedOutcomeModel(model_candidates()[0], folds=4, seed=99)
    p1 = first.fit_predict_oof(data.features, data.action, data.monetary_outcome, data.arms)
    p2 = second.fit_predict_oof(data.features, data.action, data.monetary_outcome, data.arms)
    assert p1.shape == (len(data.action), data.arms)
    assert np.array_equal(first.fold_id_, second.fold_id_)
    assert np.allclose(p1, p2)
    assert first.fold_id_ is not None and np.all(first.fold_id_ >= 0)


@pytest.mark.parametrize("candidate", model_candidates(seed=8))
def test_all_model_candidates_produce_finite_multi_arm_predictions(candidate: object) -> None:
    data = _rct(n=360)
    model = CrossFittedOutcomeModel(candidate, folds=3, seed=8)  # type: ignore[arg-type]
    oof = model.fit_predict_oof(data.features, data.action, data.monetary_outcome, data.arms)
    assert oof.shape == (360, 3)
    assert np.all(np.isfinite(oof))


def test_two_part_recomposition_is_nonnegative() -> None:
    data = _rct(n=360)
    candidate = next(model for model in model_candidates() if model.name.startswith("two_part"))
    fitted = CrossFittedOutcomeModel(candidate, folds=3)
    assert np.all(
        fitted.fit_predict_oof(data.features, data.action, data.monetary_outcome, data.arms) >= 0
    )


def test_policy_subtracts_action_cost_and_never_selects_prohibited_action() -> None:
    data = _rct()
    engine = EconomicPolicyEngine(
        CrossFittedOutcomeModel(model_candidates()[0], folds=3), minimum_arm_rows=20
    )
    engine.fit(data)
    costs = data.action_cost.copy()
    costs[:, 1] = 100.0
    allowed = data.allowed_actions.copy()
    allowed[:, 2] = False
    decision = engine.decide(data.features[:50], costs[:50], allowed[:50])
    assert np.all(decision.chosen_action == 0)
    assert not np.any(decision.chosen_action == 2)


def test_dr_policy_value_matches_known_toy_rct_direction() -> None:
    data = _rct(n=6_000)
    nuisance = np.column_stack(
        [
            2.0 + 0.3 * data.features[:, 0],
            2.5 + 0.3 * data.features[:, 0],
            1.7 + 0.3 * data.features[:, 0],
        ]
    )
    result = evaluate_policy(
        data, np.ones(len(data.action), dtype=np.int64), nuisance, estimator="dr"
    )
    bau = evaluate_policy(
        data, np.zeros(len(data.action), dtype=np.int64), nuisance, estimator="dr"
    )
    assert result.value_per_unit > bau.value_per_unit
    assert result.effective_sample_size > 1_500
    assert result.lower_95 < result.value_per_unit < result.upper_95


def test_ipw_hajek_and_clipping_are_reported() -> None:
    data = _rct(n=900)
    nuisance = np.zeros((900, 3))
    policy = np.ones(900, dtype=np.int64)
    ipw = evaluate_policy(data, policy, nuisance, estimator="ipw", weight_clip=2.0)
    hajek = evaluate_policy(data, policy, nuisance, estimator="hajek")
    assert ipw.clipped_fraction > 0
    assert hajek.max_weight == pytest.approx(3.0)


def test_claim_authority_prevents_revenue_being_called_profit() -> None:
    with pytest.raises(ValueError, match="cost components"):
        ClaimAuthority(
            level=ClaimLevel.REAL_RANDOMIZED_CONTRIBUTION_PROFIT,
            randomized=True,
            real_world=True,
            monetary_outcome=True,
            observed_revenue=True,
            declared_action_costs=True,
            label="profit",
        )
    authority = ClaimAuthority(
        level=ClaimLevel.REAL_RANDOMIZED_ECONOMIC_VALUE_UNDER_DECLARED_COSTS,
        randomized=True,
        real_world=True,
        monetary_outcome=True,
        observed_revenue=True,
        declared_action_costs=True,
        label="economic value under cost scenario",
    )
    assert authority.level == ClaimLevel.REAL_RANDOMIZED_ECONOMIC_VALUE_UNDER_DECLARED_COSTS


def test_split_is_deterministic_disjoint_and_persists_hashes_only(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("treatment\nA\nB\n")
    units = [f"customer-{index}" for index in range(200)]
    treatments = ["A" if index % 2 else "B" for index in range(200)]
    manifest = build_split_manifest(
        dataset="fixture",
        dataset_path=source,
        unit_ids=units,
        treatments=treatments,
        split_seed=72,
        source_commit="abc",
        source_tree_sha256="def",
    )
    sets = [set(manifest.unit_hashes[name]) for name in manifest.unit_hashes]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert sum(manifest.row_counts.values()) == 200
    assert stable_unit_hash("fixture", units[0]) in set.union(*sets)
    assert assigned_split("fixture", units[0], 72) == assigned_split("fixture", units[0], 72)
    path = tmp_path / "manifest.json"
    write_manifest_immutable(manifest, path)
    assert "customer-" not in path.read_text()
    write_manifest_immutable(manifest, path)


def test_sealed_guard_fails_closed_and_is_one_time(tmp_path: Path) -> None:
    freeze = FreezeManifest("s", "d", "m", "model", "threshold", True, True, 3)
    guard = SealedTestGuard(tmp_path)
    assert guard.authorize_once(freeze, freeze) == freeze.freeze_sha256
    with pytest.raises(PermissionError, match="already consumed"):
        guard.authorize_once(freeze, freeze)
    with pytest.raises(PermissionError, match="changed"):
        SealedTestGuard(tmp_path / "other").authorize_once(
            freeze, replace(freeze, source_sha256="x")
        )


def test_sealed_guard_requires_three_datasets_and_all_gates(tmp_path: Path) -> None:
    base = FreezeManifest("s", "d", "m", "model", "threshold", True, True, 2)
    with pytest.raises(PermissionError, match="three qualified"):
        SealedTestGuard(tmp_path).authorize_once(base, base)
    failed = replace(base, qualified_datasets=3, sequential_passed=False)
    with pytest.raises(PermissionError, match="gates"):
        SealedTestGuard(tmp_path).authorize_once(failed, failed)


def test_first_credible_mature_harm_pauses_immediately() -> None:
    controller = SequentialController()
    evidence = (EvidenceBatch("b", 3, -0.8, 0.1),)
    decision = controller.decide(
        current_state=LifecycleState.ACTIVE,
        current_period=3,
        mature_evidence=evidence,
        support_valid=True,
        assignment_integrity_valid=True,
    )
    assert decision.state is LifecycleState.PAUSED
    assert not decision.allow_new_exposure
    assert decision.harm_latched


def test_identical_observable_history_yields_identical_decision_and_ignores_future() -> None:
    controller = SequentialController()
    visible = EvidenceBatch("visible", 2, 0.5, 0.1)
    future = EvidenceBatch("future", 9, -10.0, 0.0)
    kwargs = dict(
        current_state=LifecycleState.TEST,
        current_period=3,
        support_valid=True,
        assignment_integrity_valid=True,
    )
    first = controller.decide(mature_evidence=(visible,), **kwargs)
    second = controller.decide(mature_evidence=(visible, future), **kwargs)
    assert first == second


def test_expired_evidence_forces_revalidation_and_support_fails_closed() -> None:
    controller = SequentialController(SequentialControllerConfig(freshness_periods=2))
    stale = (EvidenceBatch("old", 1, 0.8, 0.05),)
    expired = controller.decide(
        current_state=LifecycleState.ACTIVE,
        current_period=5,
        mature_evidence=stale,
        support_valid=True,
        assignment_integrity_valid=True,
    )
    unsupported = controller.decide(
        current_state=LifecycleState.ACTIVE,
        current_period=5,
        mature_evidence=stale,
        support_valid=False,
        assignment_integrity_valid=True,
    )
    assert expired.state is LifecycleState.REVALIDATING
    assert unsupported.state is LifecycleState.PAUSED
    assert not unsupported.allow_new_exposure


def test_sequential_controller_has_no_oracle_or_true_effect_input() -> None:
    parameters = set(signature(SequentialController.decide).parameters)
    assert not any("oracle" in name or "true_effect" in name for name in parameters)


def test_sequential_paths_stop_without_continuation_and_can_reactivate() -> None:
    harmful = run_path("HARMFUL", 999_001)
    reactivation = run_path("REACTIVATION", 999_002)
    assert harmful.stop_latency == 0
    assert harmful.harmful_assignments_after_observation == 0
    assert not harmful.early_risk_release
    assert reactivation.reactivated
    assert reactivation.harmful_revalidation_assignments <= 10
