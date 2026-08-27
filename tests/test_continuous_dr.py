import numpy as np
import polars as pl
import pytest

from decision_engine.causal.continuous_dr import (
    ConditionalTreatmentDensity,
    ContinuousDRDoseResponseEstimator,
)
from decision_engine.decision.continuous_engine import ContinuousDecisionEngine
from decision_engine.decision.continuous_support import (
    ConditionalSupportConfig,
    ConditionalSupportGate,
    ConditionalSupportReport,
)
from decision_engine.metrics.continuous import counterfactual_calibration_metrics
from decision_engine.synthetic.retail.world import RetailWorldConfig, generate_retail_world
from decision_engine.uncertainty.continuous_bootstrap import (
    CounterfactualBootstrapResult,
    bootstrap_counterfactual_curve,
)

FEATURES = [
    "store_id",
    "category_id",
    "sku_id",
    "regular_price",
    "inventory",
    "weekday",
    "holiday",
    "marketing",
    "competitor_signal",
    "product_age",
    "lagged_demand",
    "unit_cost",
]


def compact_world(seed: int = 4, support: str = "good"):
    return generate_retail_world(
        RetailWorldConfig(
            stores=1, categories=2, skus=4, days=40, seed=seed, support=support
        )
    )


def fit_dr(seed: int = 4, support: str = "good"):
    world = compact_world(seed, support)
    cutoff = int(world.frame.height * 0.7)
    estimator = ContinuousDRDoseResponseEstimator(
        outcome_kind="parametric",
        density_kind="gaussian",
        n_splits=2,
        seed=seed,
    ).fit(world.frame[:cutoff], FEATURES)
    return world, cutoff, estimator


def test_cross_fitting_has_no_training_row_leakage_and_is_chronological() -> None:
    _, _, estimator = fit_dr()
    for fold in estimator.crossfit_folds_:
        assert set(fold.train_rows).isdisjoint(fold.validation_rows)
        assert fold.train_max_date < fold.validation_min_date


def test_dr_estimator_is_deterministic() -> None:
    world, cutoff, first = fit_dr(seed=6)
    second = ContinuousDRDoseResponseEstimator(
        outcome_kind="parametric", density_kind="gaussian", n_splits=2, seed=6
    ).fit(world.frame[:cutoff], FEATURES)
    doses = np.array([0.0, 0.1, 0.2])
    assert np.allclose(
        first.dose_response(world.frame[cutoff : cutoff + 10], doses),
        second.dose_response(world.frame[cutoff : cutoff + 10], doses),
    )


@pytest.mark.parametrize("kind", ["gaussian", "kernel_residual"])
def test_treatment_density_is_finite(kind: str) -> None:
    world = compact_world()
    model = ConditionalTreatmentDensity(kind=kind).fit(world.frame, FEATURES)
    density = model.density(world.frame[:5], np.array([0.0, 0.1, 0.2]))
    assert density.shape == (5, 3)
    assert np.all(np.isfinite(density))
    assert np.all(density >= 0)


def test_density_clipping_is_reported() -> None:
    _, _, estimator = fit_dr(support="bad")
    diagnostics = estimator.density_diagnostics_
    assert 0 <= diagnostics.fraction_clipped <= 1
    assert diagnostics.minimum_effective_density >= diagnostics.floor
    assert diagnostics.effective_sample_size > 0


def test_conditional_support_rejects_unseen_dose_and_accepts_observed_region() -> None:
    world, cutoff, estimator = fit_dr(support="bad")
    history = world.frame[:cutoff]
    state = world.frame[cutoff : cutoff + 5]
    gate = ConditionalSupportGate(
        estimator.density_model_,
        ConditionalSupportConfig(minimum_local_ess=3, strong_local_ess=8),
    ).fit(history, FEATURES)
    observed = gate.report(state, 0.01)
    unseen = gate.report(state, 0.25)
    assert observed.support_level in {"SUPPORTED", "LIMITED"}
    assert unseen.support_level == "UNSUPPORTED"
    assert unseen.extrapolation_score > observed.extrapolation_score


def test_unsupported_optimum_never_acts() -> None:
    world, cutoff, estimator = fit_dr(support="bad")
    engine = ContinuousDecisionEngine(estimator)
    engine.history_ = world.frame[:cutoff]
    engine.features_ = FEATURES
    engine.support_gate_ = ConditionalSupportGate(estimator.density_model_).fit(
        engine.history_, FEATURES
    )
    result = engine.recommend(world.frame[cutoff : cutoff + 10], np.array([0.20, 0.25, 0.30]))
    assert result.status == "ABSTAIN"
    assert result.dose is None


def test_clustered_bootstrap_is_deterministic_and_ordered() -> None:
    world, cutoff, estimator = fit_dr(seed=8)
    kwargs = dict(
        estimator=estimator,
        history=world.frame[:cutoff],
        state=world.frame[cutoff : cutoff + 8],
        features=FEATURES,
        doses=np.array([0.0, 0.1]),
        replicates=3,
        seed=91,
    )
    first = bootstrap_counterfactual_curve(**kwargs)
    second = bootstrap_counterfactual_curve(**kwargs)
    assert np.allclose(first.demand_samples, second.demand_samples)
    lower, upper = first.intervals[0.9]
    assert np.all(np.asarray(lower) <= np.asarray(upper))
    assert first.valid_replicates == 3


def test_counterfactual_calibration_fixture() -> None:
    result = counterfactual_calibration_metrics(
        np.array([1.0, 2.0]),
        np.array([0.0, 1.5]),
        np.array([1.5, 2.5]),
        nominal=0.9,
    )
    assert result["coverage"] == 1.0
    assert result["calibration_error"] == pytest.approx(0.1)
    assert result["average_width"] == 1.25


def test_oracle_truth_is_not_in_estimator_frame() -> None:
    world = compact_world()
    forbidden = {"baseline_demand", "beta", "gamma", "hidden_u", "interaction_matrix"}
    assert forbidden.isdisjoint(world.frame.columns)
    with pytest.raises(ValueError, match="features missing"):
        ContinuousDRDoseResponseEstimator(n_splits=2).fit(
            world.frame, FEATURES + ["beta"]
        )


def test_hidden_confounding_is_an_explicit_unresolved_assumption() -> None:
    world = generate_retail_world(
        RetailWorldConfig(
            stores=1,
            categories=2,
            skus=4,
            days=35,
            seed=12,
            hidden_confounding=True,
        )
    )
    estimator = ContinuousDRDoseResponseEstimator(
        outcome_kind="parametric", density_kind="gaussian", n_splits=2
    ).fit(world.frame, FEATURES)
    assert any("exchangeability" in assumption for assumption in estimator.assumptions)
    assert not any("hidden confounding solved" in item for item in estimator.assumptions)


def test_post_treatment_price_is_rejected_as_control() -> None:
    world = compact_world()
    with pytest.raises(ValueError, match="post-treatment"):
        ContinuousDRDoseResponseEstimator(n_splits=2).fit(
            world.frame, FEATURES + ["price"]
        )


def test_support_is_context_specific() -> None:
    frame = pl.DataFrame(
        {
            "discount": [0.02] * 40 + [0.20] * 40,
            "segment": ["A"] * 40 + ["B"] * 40,
            "x": np.tile(np.linspace(0, 1, 40), 2),
        }
    )

    class KnownDensity:
        def density(self, state, doses):
            target = 0.02 if state["segment"][0] == "A" else 0.20
            return np.full((state.height, len(doses)), np.exp(-((doses - target) / 0.02) ** 2))

        def observed_density(self, state):
            return np.ones(state.height)

    gate = ConditionalSupportGate(
        KnownDensity(),  # type: ignore[arg-type]
        ConditionalSupportConfig(minimum_local_ess=3, strong_local_ess=8),
    ).fit(frame, ["segment", "x"])
    report_a = gate.report(frame[:5], 0.20)
    report_b = gate.report(frame[-5:], 0.20)
    assert report_a.support_level == "UNSUPPORTED"
    assert report_b.support_level in {"SUPPORTED", "LIMITED"}


class FixedResponseEstimator:
    causal = False
    assumptions = ()

    def fit(self, frame, features):
        return self

    def dose_response(self, frame, doses):
        response = 10 + 45 * doses - 150 * doses**2
        return np.tile(response, (frame.height, 1))


def decision_fixture():
    history = pl.DataFrame({
        "discount": np.tile(np.array([0.0, 0.1, 0.2]), 120),
        "observed_sales": np.full(360, 10.0),
        "regular_price": np.full(360, 10.0),
        "unit_cost": np.full(360, 3.0),
    })
    state = history[:10]
    engine = ContinuousDecisionEngine(FixedResponseEstimator())  # type: ignore[arg-type]
    engine.history_ = history
    return engine, state


def test_decision_gate_can_act_under_strong_support() -> None:
    engine, state = decision_fixture()
    result = engine.recommend(state, np.array([0.0, 0.1, 0.2]))
    assert result.status == "ACT"
    assert result.dose == pytest.approx(0.1)


def test_flat_uncertain_profit_surface_proposes_experiment_and_range() -> None:
    engine, state = decision_fixture()
    doses = np.array([0.0, 0.1, 0.2])
    profit_samples = np.array([[70.0, 75.0, 74.5], [70.0, 74.5, 75.0], [70.0, 75.2, 74.8]])
    uncertainty = CounterfactualBootstrapResult(
        tuple(doses), (10.0, 12.0, 13.0), (1.0, 1.0, 1.0), {}, 3, 3,
        np.ones((3, 3)), profit_samples,
    )
    result = engine.recommend(state, doses, uncertainty=uncertainty, near_optimal_fraction=0.02)
    assert result.status == "EXPERIMENT"
    assert result.robust_range == (0.1, 0.2)
    assert result.experiment is not None


class UnitDensity:
    def __init__(self, scale: float = 1.0, unsupported_above: float | None = None):
        self.scale = scale
        self.unsupported_above = unsupported_above

    def density(self, state, doses):
        values = np.full((state.height, len(doses)), self.scale)
        if self.unsupported_above is not None:
            values[:, doses > self.unsupported_above] = 0.0
        return values

    def observed_density(self, state):
        return np.full(state.height, self.scale)


def conditional_decision_fixture(density, repeats: int = 30):
    history = pl.DataFrame({
        "discount": np.tile(np.array([0.0, 0.1, 0.2]), repeats),
        "observed_sales": np.full(repeats * 3, 10.0),
        "regular_price": np.full(repeats * 3, 10.0),
        "unit_cost": np.full(repeats * 3, 3.0),
        "x": np.zeros(repeats * 3),
    })
    engine = ContinuousDecisionEngine(FixedResponseEstimator())  # type: ignore[arg-type]
    engine.history_ = history
    engine.support_gate_ = ConditionalSupportGate(
        density,  # type: ignore[arg-type]
        ConditionalSupportConfig(context_neighbors=history.height),
    ).fit(history, ["x"])
    return engine, history[:10]


def test_single_soft_support_warning_does_not_veto_act() -> None:
    engine, state = conditional_decision_fixture(UnitDensity(), repeats=30)
    result = engine.recommend(state, np.array([0.0, 0.1, 0.2]))
    selected = result.support[1]
    assert result.status == "ACT"
    assert isinstance(selected, ConditionalSupportReport)
    assert selected.soft_warnings == ("moderate_ess",)
    assert result.support_reasons == ("best candidate has limited conditional support",)
    assert result.evidence_reasons == ()


def test_hard_support_violation_vetoes_act_at_unsupported_optimum() -> None:
    engine, state = conditional_decision_fixture(UnitDensity(unsupported_above=0.05))
    result = engine.recommend(state, np.array([0.0, 0.1, 0.2]))
    assert result.status == "ABSTAIN"
    assert result.withholding_layer == "SUPPORT"
    assert result.support_reasons
    assert result.evidence_reasons == ()


class NearBoundaryEstimator:
    causal = False
    assumptions = ()

    def fit(self, frame, features):
        return self

    def dose_response(self, frame, doses):
        profits = np.array([70.0, 79.6, 80.0])
        margins = 10 * (1 - doses) - 3
        return np.tile(profits / margins, (frame.height, 1))


def test_nearby_supported_near_optimal_dose_can_be_selected() -> None:
    doses = np.array([0.10, 0.12, 0.14])
    history = pl.DataFrame({
        "discount": np.tile(np.array([0.10, 0.12]), 120),
        "observed_sales": np.full(240, 10.0),
        "regular_price": np.full(240, 10.0),
        "unit_cost": np.full(240, 3.0),
        "x": np.zeros(240),
    })
    engine = ContinuousDecisionEngine(NearBoundaryEstimator())  # type: ignore[arg-type]
    engine.history_ = history
    engine.support_gate_ = ConditionalSupportGate(
        UnitDensity(unsupported_above=0.12),  # type: ignore[arg-type]
        ConditionalSupportConfig(context_neighbors=history.height),
    ).fit(history, ["x"])
    result = engine.recommend(history[:5], doses)
    assert result.status == "ACT"
    assert result.unconstrained_dose == pytest.approx(0.14)
    assert result.dose == pytest.approx(0.12)
    assert "projected" in result.support_reasons[0]


def test_raw_density_rescaling_does_not_flip_relative_support() -> None:
    history = pl.DataFrame({
        "discount": np.tile(np.array([0.0, 0.1]), 80),
        "x": np.zeros(160),
    })
    config = ConditionalSupportConfig(context_neighbors=history.height)
    low_scale = ConditionalSupportGate(
        UnitDensity(scale=0.001), config  # type: ignore[arg-type]
    ).fit(history, ["x"]).report(history[:5], 0.1)
    high_scale = ConditionalSupportGate(
        UnitDensity(scale=1000), config  # type: ignore[arg-type]
    ).fit(history, ["x"]).report(history[:5], 0.1)
    assert low_scale.support_level == high_scale.support_level
    assert low_scale.density_percentile == high_scale.density_percentile
    assert low_scale.density_ratio_to_typical == pytest.approx(
        high_scale.density_ratio_to_typical
    )


def test_support_threshold_configuration_is_deterministic_and_oracle_free() -> None:
    assert ConditionalSupportConfig() == ConditionalSupportConfig()
    fields = set(ConditionalSupportConfig.__dataclass_fields__)
    assert not any("oracle" in name or "regime" in name for name in fields)
