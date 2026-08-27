from pathlib import Path

import numpy as np
import polars as pl
import pytest

from benchmarks.ecommerce_decision_layer_v6.evaluation import (
    begin_official_reveal,
    evaluate_what_if,
)
from benchmarks.ecommerce_decision_layer_v6.run import (
    FEATURE_PATH,
    BenchmarkConfig,
    assert_final_isolation,
    development_config,
)
from benchmarks.ecommerce_decision_layer_v6.simulator import (
    ActionEvidence,
    PolicyState,
    _complexity,
    _mature,
    _opportunity_ranking,
    simulate_policy,
)
from benchmarks.ecommerce_decision_layer_v6.world import build_merchant


def _merchant(seed: int = 51):
    frame = pl.read_parquet(FEATURE_PATH)
    return build_merchant(
        frame,
        merchant_id=f"fixture-{seed}",
        regime="medium_action_value",
        seed=seed,
        volume=120,
        final=False,
    )


def test_oracle_isolation_and_discovery_signature() -> None:
    observed, truth = _merchant()
    assert not hasattr(observed, "regime")
    assert not hasattr(observed, "global_effects")
    assert hasattr(truth, "global_effects")
    first = _opportunity_ranking(observed, 0)
    mutated_truth = type(truth)(**{**truth.__dict__, "global_effects": -100 * truth.global_effects})
    assert np.array_equal(first, _opportunity_ranking(observed, 0))
    assert not np.array_equal(truth.global_effects, mutated_truth.global_effects)


def test_x5_targets_cannot_enter_materialized_customer_state() -> None:
    frame = pl.read_parquet(FEATURE_PATH)
    observed, _ = build_merchant(
        frame,
        merchant_id="original",
        regime="null",
        seed=70,
        volume=100,
        final=False,
    )
    mutated = frame.with_columns(pl.lit(999).alias("target"), pl.lit(1).alias("treatment_flg"))
    changed, _ = build_merchant(
        mutated,
        merchant_id="mutated",
        regime="null",
        seed=70,
        volume=100,
        final=False,
    )
    np.testing.assert_allclose(observed.customer_features, changed.customer_features)
    np.testing.assert_allclose(observed.pre_period_cp, changed.pre_period_cp)


def test_delayed_retention_outcome_does_not_mature_early() -> None:
    state = PolicyState()
    state.pending.append(
        (
            3,
            3,
            1,
            np.array([2.0]),
            np.array([1.0]),
            np.array([1.0, -1.0]),
            np.array([True, False]),
            np.array([0.5, -0.5]),
        )
    )
    _mature(state, 2)
    assert not state.evidence[(3, 1)].treated
    _mature(state, 3)
    assert state.evidence[(3, 1)].treated == [2.0]


def test_progressive_policy_can_promote_segment_before_global_act() -> None:
    segment = np.tile(np.array([True, False]), 300)
    scores = np.where(segment, 1.2, -0.6)
    evidence = ActionEvidence(
        treated=[1.0] * 300,
        control=[0.0] * 300,
        scores=scores.tolist(),
        segments=segment.tolist(),
        features=np.linspace(-1, 1, 600).tolist(),
        partitions=(np.arange(600) % 3).tolist(),
    )
    decision = _complexity(evidence)
    assert decision.granularity.value == "G1_SEGMENT"
    assert decision.selected_policy_lower > 0


def test_homogeneous_scores_do_not_trigger_segment_policy() -> None:
    segment = np.tile(np.array([True, False]), 300)
    evidence = ActionEvidence(
        treated=[1.0] * 300,
        control=[0.0] * 300,
        scores=np.ones(600).tolist(),
        segments=segment.tolist(),
        features=np.linspace(-1, 1, 600).tolist(),
        partitions=(np.arange(600) % 3).tolist(),
    )
    assert _complexity(evidence).granularity.value == "G0_GLOBAL"


def test_universal_bau_holdout_is_policy_invariant() -> None:
    observed, truth = _merchant(61)
    local, _ = simulate_policy(
        observed,
        truth,
        policy="v6_local_only",
        source_records=(),
        seed=800,
        horizon=3,
    )
    full, _ = simulate_policy(
        observed,
        truth,
        policy="v6_full",
        source_records=(),
        seed=800,
        horizon=3,
    )
    assert [row["bau_holdout_profit"] for row in local] == [
        row["bau_holdout_profit"] for row in full
    ]


def test_development_and_final_worlds_must_be_disjoint() -> None:
    development = development_config(quick=False)
    final = BenchmarkConfig(
        mode="official_final",
        source_seeds=(66_000,),
        target_seeds=(76_000,),
        target_regimes=("null",),
        target_volumes=(600,),
        source_volume=800,
        horizon=26,
        bootstrap_replicates=4_000,
        evaluation_seed=77_001,
    )
    assert_final_isolation(development, final)
    with pytest.raises(ValueError, match="overlap"):
        assert_final_isolation(
            development,
            BenchmarkConfig(**{**final.__dict__, "target_seeds": (development.target_seeds[0],)}),
        )


def test_one_time_reveal_guard(tmp_path: Path) -> None:
    (tmp_path / "FREEZE_MANIFEST.json").write_text("{}")
    begin_official_reveal(tmp_path)
    with pytest.raises(RuntimeError, match="already"):
        begin_official_reveal(tmp_path)


def test_what_if_calibration_evaluator() -> None:
    rows = []
    for index in range(100):
        positive = index >= 50
        truth = 1.0 if positive else -1.0
        rows.append(
            {
                "probability_positive": 0.9 if positive else 0.1,
                "true_effect": truth,
                "predicted_mean": truth,
                "lower": truth - 0.2,
                "upper": truth + 0.2,
            }
        )
    report = evaluate_what_if(rows)
    assert report.interval_coverage == 1
    assert report.sign_accuracy == 1
    assert report.brier_score < 0.02
    assert report.probability_calibration_error == pytest.approx(0.1)
