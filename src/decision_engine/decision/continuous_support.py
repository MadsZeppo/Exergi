from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from decision_engine.causal.continuous_dr import TreatmentDensityNuisance


@dataclass(frozen=True)
class DoseSupport:
    dose: float
    comparable_count: int
    nearest_distance: float
    local_density: float
    status: str
    uncertainty_multiplier: float


def continuous_dose_support(
    historical_doses: np.ndarray,
    dose: float,
    *,
    bandwidth: float = 0.025,
    minimum_comparables: int = 30,
) -> DoseSupport:
    values = np.asarray(historical_doses, dtype=float)
    distances = np.abs(values - dose)
    comparable = int(np.sum(distances <= bandwidth))
    nearest = float(distances.min()) if distances.size else float("inf")
    density = float(np.mean(np.exp(-0.5 * (distances / bandwidth) ** 2))) if values.size else 0
    if not values.size or dose < values.min() - bandwidth or dose > values.max() + bandwidth:
        status = "OUT_OF_SUPPORT"
    elif comparable < minimum_comparables:
        status = "WEAK_SUPPORT"
    elif comparable < minimum_comparables * 3:
        status = "MODERATE_SUPPORT"
    else:
        status = "STRONG_SUPPORT"
    multiplier = 1 + min(4.0, nearest / bandwidth + minimum_comparables / max(comparable, 1))
    return DoseSupport(dose, comparable, nearest, density, status, multiplier)


@dataclass(frozen=True)
class ConditionalSupportConfig:
    dose_bandwidth: float = 0.025
    context_neighbors: int = 250
    minimum_density_percentile: float = 0.01
    warning_density_percentile: float = 0.05
    minimum_density_ratio: float = 0.02
    catastrophic_local_ess: float = 5.0
    minimum_local_ess: float = 20.0
    strong_local_ess: float = 60.0
    maximum_nearest_distance: float = 0.04
    warning_nearest_distance: float = 0.025
    maximum_extrapolation_score: float = 2.5
    conditional_quantile_low: float = 0.01
    conditional_quantile_high: float = 0.99


@dataclass(frozen=True)
class SupportRuleResult:
    name: str
    value: float
    threshold: float
    comparison: str
    severity: str
    triggered: bool


@dataclass(frozen=True)
class ConditionalSupportReport:
    candidate_discount: float
    conditional_density: float
    local_ess: float
    nearest_dose_distance: float
    kernel_weighted_support: float
    population_density_ratio: float
    extrapolation_score: float
    nearest_supported_region: tuple[float, float] | None
    nuisance_disagreement: float | None
    support_level: str
    reasons: tuple[str, ...]
    density_percentile: float
    density_ratio_to_typical: float
    context_ess: float
    kernel_ess: float
    local_dose_spacing: float
    conditional_quantile_region: tuple[float, float] | None
    density_clipped: bool
    hard_failures: tuple[str, ...]
    soft_warnings: tuple[str, ...]
    rules: tuple[SupportRuleResult, ...]


class ConditionalSupportGate:
    """Context-conditional dose support; thresholds are explicit and configurable."""

    def __init__(
        self,
        density_model: TreatmentDensityNuisance,
        config: ConditionalSupportConfig | None = None,
    ) -> None:
        self.density_model = density_model
        self.config = config or ConditionalSupportConfig()

    def fit(self, history: pl.DataFrame, features: list[str]) -> ConditionalSupportGate:
        self.history_ = history
        self.features_ = list(features)
        self.numeric_ = [name for name in features if history.schema[name] != pl.String]
        self.categorical_ = [name for name in features if history.schema[name] == pl.String]
        if self.numeric_:
            values = history.select(self.numeric_).to_numpy().astype(float)
            self.center_ = np.nanmedian(values, axis=0)
            self.scale_ = np.nanstd(values, axis=0)
            self.scale_[self.scale_ < 1e-8] = 1.0
            self.history_numeric_ = (values - self.center_) / self.scale_
        observed_density = self.density_model.observed_density(history)
        finite = observed_density[np.isfinite(observed_density) & (observed_density >= 0)]
        self.observed_density_ = finite if finite.size else np.array([0.0])
        self.typical_density_ = max(float(np.median(self.observed_density_)), 1e-12)
        return self

    @staticmethod
    def _weighted_quantile(
        values: np.ndarray, weights: np.ndarray, quantile: float
    ) -> float:
        order = np.argsort(values)
        ordered_values = values[order]
        ordered_weights = weights[order]
        cumulative = np.cumsum(ordered_weights)
        if not cumulative.size or cumulative[-1] <= 0:
            return float("nan")
        return float(np.interp(quantile * cumulative[-1], cumulative, ordered_values))

    def _context_weights(self, state: pl.DataFrame) -> np.ndarray:
        weights = np.ones(self.history_.height)
        if self.numeric_:
            query = np.nanmedian(state.select(self.numeric_).to_numpy().astype(float), axis=0)
            query = (query - self.center_) / self.scale_
            distance = np.sqrt(np.mean((self.history_numeric_ - query) ** 2, axis=1))
            rank = np.argsort(distance, kind="stable")
            keep = rank[: min(self.config.context_neighbors, rank.size)]
            weights[:] = 0.0
            local_scale = max(float(np.median(distance[keep])), 0.25)
            weights[keep] = np.exp(-0.5 * (distance[keep] / local_scale) ** 2)
        for name in self.categorical_:
            modes = state[name].mode().to_list()
            if modes:
                weights *= np.where(self.history_[name].to_numpy() == modes[0], 1.0, 0.15)
        return weights

    def report(
        self,
        state: pl.DataFrame,
        dose: float,
        *,
        alternative_density: np.ndarray | None = None,
    ) -> ConditionalSupportReport:
        config = self.config
        context = self._context_weights(state)
        distances = np.abs(self.history_["discount"].to_numpy() - dose)
        dose_kernel = np.exp(-0.5 * (distances / config.dose_bandwidth) ** 2)
        local = context * dose_kernel
        context_ess = (
            float(context.sum() ** 2 / np.sum(context**2)) if np.sum(context**2) else 0.0
        )
        kernel_ess = float(local.sum() ** 2 / np.sum(local**2)) if np.sum(local**2) else 0.0
        local_ess = kernel_ess
        comparable = (
            context >= np.quantile(context[context > 0], 0.5)
            if np.any(context > 0)
            else context > 0
        )
        nearest = float(distances[comparable].min()) if comparable.any() else float("inf")
        supported_values = self.history_["discount"].to_numpy()[
            comparable & (dose_kernel >= np.exp(-0.5))
        ]
        region = (
            (float(supported_values.min()), float(supported_values.max()))
            if supported_values.size
            else None
        )
        conditional = self.density_model.density(state, np.array([dose]))[:, 0]
        conditional_density = float(np.median(conditional))
        density_percentile = float(np.mean(self.observed_density_ <= conditional_density))
        density_ratio = conditional_density / self.typical_density_
        population_density = float(
            np.median(self.density_model.density(self.history_, np.array([dose]))[:, 0])
        )
        ratio = conditional_density / max(population_density, 1e-12)
        historical_doses = self.history_["discount"].to_numpy()
        quantile_low = self._weighted_quantile(
            historical_doses, context, config.conditional_quantile_low
        )
        quantile_high = self._weighted_quantile(
            historical_doses, context, config.conditional_quantile_high
        )
        quantile_region = (
            (quantile_low, quantile_high)
            if np.isfinite(quantile_low) and np.isfinite(quantile_high)
            else None
        )
        outside_distance = 0.0
        if quantile_region is not None:
            outside_distance = max(quantile_low - dose, dose - quantile_high, 0.0)
        extrapolation = outside_distance / config.dose_bandwidth
        comparable_doses = np.sort(historical_doses[comparable])
        nearest_positions = np.argsort(
            np.abs(comparable_doses - dose), kind="stable"
        )[:10]
        local_values = np.sort(comparable_doses[nearest_positions])
        spacing = (
            float(np.median(np.diff(local_values))) if local_values.size > 1 else float("inf")
        )
        disagreement = None
        if alternative_density is not None:
            primary = max(conditional_density, 1e-12)
            disagreement = float(abs(np.median(alternative_density) - primary) / primary)
        density_clipped = not np.isfinite(conditional_density) or conditional_density <= 1e-12
        rules = (
            SupportRuleResult(
                "density_percentile_hard", density_percentile,
                config.minimum_density_percentile, "<", "HARD",
                density_percentile < config.minimum_density_percentile,
            ),
            SupportRuleResult(
                "density_percentile_soft", density_percentile,
                config.warning_density_percentile, "<", "SOFT",
                density_percentile < config.warning_density_percentile,
            ),
            SupportRuleResult(
                "density_ratio_hard", density_ratio, config.minimum_density_ratio,
                "<", "HARD", density_ratio < config.minimum_density_ratio,
            ),
            SupportRuleResult(
                "local_ess_hard", local_ess, config.catastrophic_local_ess,
                "<", "HARD", local_ess < config.catastrophic_local_ess,
            ),
            SupportRuleResult(
                "local_ess_soft", local_ess, config.minimum_local_ess,
                "<", "SOFT", local_ess < config.minimum_local_ess,
            ),
            SupportRuleResult(
                "nearest_distance_hard", nearest, config.maximum_nearest_distance,
                ">", "HARD", nearest > config.maximum_nearest_distance,
            ),
            SupportRuleResult(
                "nearest_distance_soft", nearest, config.warning_nearest_distance,
                ">", "SOFT", nearest > config.warning_nearest_distance,
            ),
            SupportRuleResult(
                "extrapolation_hard", extrapolation, config.maximum_extrapolation_score,
                ">", "HARD", extrapolation > config.maximum_extrapolation_score,
            ),
            SupportRuleResult(
                "density_invalid", float(density_clipped), 0.0,
                ">", "HARD", density_clipped,
            ),
            SupportRuleResult(
                "moderate_ess", local_ess, config.strong_local_ess,
                "<", "SOFT", local_ess < config.strong_local_ess,
            ),
        )
        hard_failures = tuple(
            rule.name for rule in rules if rule.severity == "HARD" and rule.triggered
        )
        soft_warnings = tuple(
            rule.name for rule in rules if rule.severity == "SOFT" and rule.triggered
        )
        reasons = hard_failures + soft_warnings
        if hard_failures:
            level = "UNSUPPORTED"
        elif soft_warnings:
            level = "LIMITED"
        else:
            level = "SUPPORTED"
        return ConditionalSupportReport(
            dose,
            conditional_density,
            local_ess,
            nearest,
            float(local.sum()),
            ratio,
            extrapolation,
            region,
            disagreement,
            level,
            reasons,
            density_percentile,
            density_ratio,
            context_ess,
            kernel_ess,
            spacing,
            quantile_region,
            density_clipped,
            hard_failures,
            soft_warnings,
            rules,
        )


SUPPORT_ABLATIONS = (
    "density_only",
    "local_ess_only",
    "geometry_only",
    "extrapolation_only",
    "density_ess",
    "density_geometry",
    "full_gate",
)


def classify_support_ablation(
    report: ConditionalSupportReport, ablation: str
) -> str:
    if ablation not in SUPPORT_ABLATIONS:
        raise ValueError(f"unknown support ablation: {ablation}")
    if ablation == "full_gate":
        return report.support_level
    prefixes = {
        "density_only": ("density_",),
        "local_ess_only": ("local_ess_", "moderate_ess"),
        "geometry_only": ("nearest_distance_",),
        "extrapolation_only": ("extrapolation_",),
        "density_ess": ("density_", "local_ess_", "moderate_ess"),
        "density_geometry": ("density_", "nearest_distance_", "extrapolation_"),
    }[ablation]
    selected = tuple(
        rule for rule in report.rules if any(rule.name.startswith(prefix) for prefix in prefixes)
    )
    if any(rule.triggered and rule.severity == "HARD" for rule in selected):
        return "UNSUPPORTED"
    if any(rule.triggered and rule.severity == "SOFT" for rule in selected):
        return "LIMITED"
    return "SUPPORTED"
