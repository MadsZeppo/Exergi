"""Transparent normal-normal merchant partial pooling with transport gating."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class TransportSupport(StrEnum):
    HIGH_TRANSPORT_SUPPORT = "HIGH_TRANSPORT_SUPPORT"
    PARTIAL_TRANSPORT_SUPPORT = "PARTIAL_TRANSPORT_SUPPORT"
    LOW_TRANSPORT_SUPPORT = "LOW_TRANSPORT_SUPPORT"
    NO_TRANSPORT = "NO_TRANSPORT"


@dataclass(frozen=True)
class TransportReport:
    descriptor_distance: float
    action_compatible: bool
    effect_compatible: bool
    overlap: float
    freshness: float
    support: TransportSupport
    source_weight: float


@dataclass(frozen=True)
class NormalEffect:
    mean: float
    variance: float


def transport_report(
    source_descriptors: np.ndarray,
    target_descriptors: np.ndarray,
    *,
    action_compatible: bool,
    source_effect: NormalEffect,
    target_pilot: NormalEffect | None,
    overlap: float,
    freshness: float,
) -> TransportReport:
    source = np.asarray(source_descriptors, dtype=float)
    target = np.asarray(target_descriptors, dtype=float)
    if source.shape != target.shape or not 0 <= overlap <= 1 or not 0 <= freshness <= 1:
        raise ValueError("invalid transport inputs")
    distance = float(np.linalg.norm(source - target) / np.sqrt(max(1, source.size)))
    compatible = True
    if target_pilot is not None:
        joint_se = np.sqrt(max(1e-12, source_effect.variance + target_pilot.variance))
        compatible = abs(source_effect.mean - target_pilot.mean) <= 2.5 * joint_se
        adversarial = (
            source_effect.mean * target_pilot.mean < 0
            and abs(source_effect.mean) > 1.96 * np.sqrt(source_effect.variance)
            and abs(target_pilot.mean) > 1.96 * np.sqrt(target_pilot.variance)
        )
    else:
        adversarial = False
    if not action_compatible or adversarial or distance > 3 or overlap < 0.1:
        support = TransportSupport.NO_TRANSPORT
        weight = 0.0
    else:
        weight = float(np.exp(-distance) * overlap * freshness * (1.0 if compatible else 0.2))
        if weight >= 0.60:
            support = TransportSupport.HIGH_TRANSPORT_SUPPORT
        elif weight >= 0.25:
            support = TransportSupport.PARTIAL_TRANSPORT_SUPPORT
        elif weight > 0:
            support = TransportSupport.LOW_TRANSPORT_SUPPORT
        else:
            support = TransportSupport.NO_TRANSPORT
    return TransportReport(
        descriptor_distance=distance,
        action_compatible=action_compatible,
        effect_compatible=compatible,
        overlap=overlap,
        freshness=freshness,
        support=support,
        source_weight=weight,
    )


def partial_pool(
    prior: NormalEffect,
    local_estimate: NormalEffect | None,
    *,
    transport_weight: float,
) -> NormalEffect:
    if not 0 <= transport_weight <= 1 or prior.variance <= 0:
        raise ValueError("invalid prior or transport weight")
    if local_estimate is None:
        if transport_weight == 0:
            return NormalEffect(0.0, float("inf"))
        return NormalEffect(prior.mean, prior.variance / transport_weight)
    if local_estimate.variance <= 0:
        raise ValueError("local variance must be positive")
    prior_precision = transport_weight / prior.variance
    local_precision = 1 / local_estimate.variance
    total = prior_precision + local_precision
    mean = (prior.mean * prior_precision + local_estimate.mean * local_precision) / total
    return NormalEffect(mean=float(mean), variance=float(1 / total))
