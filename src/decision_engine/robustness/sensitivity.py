from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinearSensitivityResult:
    estimated_effect: float
    standard_error: float
    partial_r2_y: float
    partial_r2_treatment: float
    adjusted_effect: float
    robustness_value: float
    interpretation: str


def linear_partial_r2_sensitivity(
    effect: float,
    standard_error: float,
    degrees_of_freedom: int,
    *,
    partial_r2_y: float,
    partial_r2_treatment: float,
) -> LinearSensitivityResult:
    """Transparent Cinelli-Hazlett-inspired approximation for linear estimators only."""
    if standard_error <= 0 or degrees_of_freedom <= 0:
        raise ValueError("positive standard error and degrees of freedom required")
    if not 0 <= partial_r2_y < 1 or not 0 <= partial_r2_treatment < 1:
        raise ValueError("partial R-squared values must lie in [0, 1)")
    bias_scale = standard_error * (degrees_of_freedom**0.5)
    bias = bias_scale * ((partial_r2_y * partial_r2_treatment) / (1 - partial_r2_treatment)) ** 0.5
    adjusted = effect - (1 if effect >= 0 else -1) * bias
    signal = abs(effect) / bias_scale
    robustness = float((2 * signal) / (signal + (signal**2 + 4) ** 0.5)) if signal else 0.0
    label = "HIGH" if robustness >= 0.2 else "MODERATE" if robustness >= 0.1 else "LOW"
    return LinearSensitivityResult(
        effect, standard_error, partial_r2_y, partial_r2_treatment, adjusted, robustness, label
    )
