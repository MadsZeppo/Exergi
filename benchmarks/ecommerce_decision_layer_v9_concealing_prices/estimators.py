"""Frozen design-based estimators for V9."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class Estimate:
    point: float
    standard_error: float
    lower_95: float
    upper_95: float
    n_control: int
    n_treatment: int
    method: str

    def as_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def difference_in_means(outcome: np.ndarray, treatment: np.ndarray) -> Estimate:
    control = outcome[treatment == 0]
    treated = outcome[treatment == 1]
    if len(control) < 2 or len(treated) < 2:
        raise ValueError("both randomized arms require at least two observations")
    point = float(treated.mean() - control.mean())
    standard_error = float(
        np.sqrt(treated.var(ddof=1) / len(treated) + control.var(ddof=1) / len(control))
    )
    critical = float(stats.norm.ppf(0.975))
    return Estimate(
        point=point,
        standard_error=standard_error,
        lower_95=point - critical * standard_error,
        upper_95=point + critical * standard_error,
        n_control=len(control),
        n_treatment=len(treated),
        method="design-based difference in raw means; Neyman SE; normal 95% CI",
    )


def paired_difference(contrasts: np.ndarray) -> Estimate:
    if len(contrasts) < 2:
        raise ValueError("paired estimator requires at least two date blocks")
    point = float(contrasts.mean())
    standard_error = float(contrasts.std(ddof=1) / np.sqrt(len(contrasts)))
    critical = float(stats.t.ppf(0.975, df=len(contrasts) - 1))
    return Estimate(
        point=point,
        standard_error=standard_error,
        lower_95=point - critical * standard_error,
        upper_95=point + critical * standard_error,
        n_control=len(contrasts),
        n_treatment=len(contrasts),
        method="paired date contrast; Student-t 95% CI",
    )


def arm_stratified_bootstrap(
    outcome: np.ndarray,
    treatment: np.ndarray,
    *,
    replicates: int,
    seed: int,
) -> dict[str, float | int]:
    control = outcome[treatment == 0]
    treated = outcome[treatment == 1]
    rng = np.random.default_rng(seed)
    values = np.empty(replicates)
    for index in range(replicates):
        control_mean = float(rng.choice(control, size=len(control), replace=True).mean())
        treated_mean = float(rng.choice(treated, size=len(treated), replace=True).mean())
        values[index] = treated_mean - control_mean
    return {
        "replicates": replicates,
        "bootstrap_standard_error": float(values.std(ddof=1)),
        "lower_95": float(np.quantile(values, 0.025)),
        "median": float(np.quantile(values, 0.5)),
        "upper_95": float(np.quantile(values, 0.975)),
    }


def paired_bootstrap(
    contrasts: np.ndarray, *, replicates: int, seed: int
) -> dict[str, float | int]:
    rng = np.random.default_rng(seed)
    values = np.empty(replicates)
    for index in range(replicates):
        values[index] = float(rng.choice(contrasts, size=len(contrasts), replace=True).mean())
    return {
        "replicates": replicates,
        "bootstrap_standard_error": float(values.std(ddof=1)),
        "lower_95": float(np.quantile(values, 0.025)),
        "median": float(np.quantile(values, 0.5)),
        "upper_95": float(np.quantile(values, 0.975)),
    }


def permutation_p_value(
    outcome: np.ndarray,
    treatment: np.ndarray,
    *,
    replicates: int,
    seed: int,
) -> float:
    observed = abs(difference_in_means(outcome, treatment).point)
    rng = np.random.default_rng(seed)
    exceedances = 0
    shuffled = treatment.copy()
    for _ in range(replicates):
        rng.shuffle(shuffled)
        candidate = abs(float(outcome[shuffled == 1].mean() - outcome[shuffled == 0].mean()))
        exceedances += int(candidate >= observed)
    return (exceedances + 1.0) / (replicates + 1.0)


def paired_sign_permutation_p_value(
    contrasts: np.ndarray, *, replicates: int, seed: int
) -> float:
    observed = abs(float(contrasts.mean()))
    rng = np.random.default_rng(seed)
    signs = np.empty(len(contrasts))
    exceedances = 0
    for _ in range(replicates):
        signs[:] = rng.choice(np.array([-1.0, 1.0]), size=len(contrasts), replace=True)
        exceedances += int(abs(float((contrasts * signs).mean())) >= observed)
    return (exceedances + 1.0) / (replicates + 1.0)


def heavy_tail_diagnostics(outcome: np.ndarray) -> dict[str, float]:
    sorted_values = np.sort(outcome)
    total = float(sorted_values.sum())
    top_count = max(1, int(np.ceil(len(sorted_values) * 0.01)))
    return {
        "zero_fraction": float(np.mean(outcome == 0)),
        "mean": float(outcome.mean()),
        "standard_deviation": float(outcome.std(ddof=1)),
        "median": float(np.median(outcome)),
        "p95": float(np.quantile(outcome, 0.95)),
        "p99": float(np.quantile(outcome, 0.99)),
        "p999": float(np.quantile(outcome, 0.999)),
        "maximum": float(outcome.max()),
        "top_1_percent_revenue_share": (
            float(sorted_values[-top_count:].sum() / total) if total else 0.0
        ),
    }


def srm_p_value(treatment: np.ndarray, expected_probability: float = 0.5) -> float:
    observed = np.bincount(treatment, minlength=2)
    expected = np.array(
        [len(treatment) * (1 - expected_probability), len(treatment) * expected_probability]
    )
    return float(stats.chisquare(observed, expected).pvalue)
