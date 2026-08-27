import duckdb

from decision_engine.dashboard.data import data_health_summary, synthetic_research_dataset
from decision_engine.decision.experiment import two_arm_sample_size
from decision_engine.registry.store import ModelPerformanceRegistry


def test_experiment_sample_size_sanity() -> None:
    assert two_arm_sample_size(outcome_standard_deviation=10, minimum_detectable_effect=5) == 63
    assert two_arm_sample_size(outcome_standard_deviation=20, minimum_detectable_effect=5) > 200


def test_registry_is_append_only(tmp_path) -> None:
    registry = ModelPerformanceRegistry(tmp_path / "registry.duckdb")
    kwargs = dict(
        record_id="fixed",
        model="m",
        dataset="d",
        regime="r",
        decision_type="forecast",
        metrics={"wape": 0.2},
        model_version="1",
    )
    registry.append(**kwargs)
    assert len(registry.records()) == 1
    try:
        registry.append(**kwargs)
    except duckdb.ConstraintException:
        pass
    else:
        raise AssertionError("duplicate registry record was accepted")
    registry.close()


def test_dashboard_data_functions_without_streamlit_runtime() -> None:
    frame = synthetic_research_dataset(days=30, entities=3)
    summary = data_health_summary(frame)
    assert summary["observations"] == 90
    assert summary["entities"] == 3
    assert summary["actions"] >= 2


def test_registry_supports_behavior_model_tournament(tmp_path) -> None:
    registry = ModelPerformanceRegistry(tmp_path / "registry.duckdb")
    registry.append_behavior_model_result(
        record_id="mt-lift-tlearner",
        decision_type="coupon",
        data_regime="randomized",
        model="t_learner",
        factual_error={"log_loss": 0.2},
        causal_error={"ate_mae": 0.01},
        calibration={"coverage_90": 0.88},
        economic_regret=0.002,
        metadata={"dataset": "MT-LIFT"},
    )
    row = registry.connection.execute(
        "SELECT model, data_regime, economic_regret FROM behavior_model_tournament_v1"
    ).fetchone()
    assert row == ("t_learner", "randomized", 0.002)
    registry.close()


def test_registry_resolves_empirical_default_by_decision_type(tmp_path) -> None:
    registry = ModelPerformanceRegistry(tmp_path / "registry.duckdb")
    registry.set_decision_model_default(
        decision_type="binary_ad_targeting",
        model="s_learner",
        selection_artifact="selection.json",
        customer_facing_do_this_enabled=False,
    )
    assert registry.selected_model("binary_ad_targeting") == "s_learner"
    assert registry.selected_model("continuous_discount") is None
    registry.close()
