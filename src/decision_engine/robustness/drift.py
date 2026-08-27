from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance


@dataclass(frozen=True)
class FeatureShift:
    feature: str
    psi: float
    wasserstein_standardized: float
    ks_statistic: float
    severity: str


@dataclass(frozen=True)
class DistributionShiftReport:
    overall: str
    features: tuple[FeatureShift, ...]


def population_stability_index(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts = np.histogram(reference, bins=edges)[0] / reference.size
    cur_counts = np.histogram(current, bins=edges)[0] / current.size
    ref_counts, cur_counts = np.clip(ref_counts, 1e-6, None), np.clip(cur_counts, 1e-6, None)
    return float(np.sum((cur_counts - ref_counts) * np.log(cur_counts / ref_counts)))


def distribution_shift_report(
    reference: dict[str, np.ndarray], current: dict[str, np.ndarray]
) -> DistributionShiftReport:
    common = sorted(set(reference) & set(current))
    if not common:
        raise ValueError("no common numerical features")
    features: list[FeatureShift] = []
    order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3}
    for name in common:
        ref, cur = np.asarray(reference[name], dtype=float), np.asarray(current[name], dtype=float)
        ref, cur = ref[np.isfinite(ref)], cur[np.isfinite(cur)]
        if not ref.size or not cur.size:
            continue
        psi = population_stability_index(ref, cur)
        scale = max(float(np.std(ref)), 1e-12)
        wasserstein = float(wasserstein_distance(ref, cur) / scale)
        ks = float(ks_2samp(ref, cur).statistic)
        if psi >= 0.5 or wasserstein >= 2 or ks >= 0.5:
            severity = "SEVERE"
        elif psi >= 0.25 or wasserstein >= 1 or ks >= 0.3:
            severity = "HIGH"
        elif psi >= 0.1 or wasserstein >= 0.5 or ks >= 0.15:
            severity = "MODERATE"
        else:
            severity = "LOW"
        features.append(FeatureShift(name, psi, wasserstein, ks, severity))
    overall = max(
        (item.severity for item in features), key=lambda value: order[value], default="LOW"
    )
    return DistributionShiftReport(
        overall, tuple(sorted(features, key=lambda x: order[x.severity], reverse=True))
    )
