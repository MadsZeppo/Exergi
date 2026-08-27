"""Minimal closed-loop matching from merchant experiment memory to next decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from .contracts import MerchantLearningRecord


class HistoricalSupport(StrEnum):
    HIGH_SUPPORT = "HIGH_SUPPORT"
    PARTIAL_SUPPORT = "PARTIAL_SUPPORT"
    STALE = "STALE"
    OUT_OF_SUPPORT = "OUT_OF_SUPPORT"


class LearnedRecommendation(StrEnum):
    ACT = "ACT"
    VERIFY = "VERIFY"
    TEST = "TEST"
    AVOID = "AVOID"


@dataclass(frozen=True)
class EvidenceMatch:
    support: HistoricalSupport
    recommendation: LearnedRecommendation
    effect: float | None
    interval: tuple[float, float] | None
    matched_records: int
    reason: str


def state_key(state: dict[str, Any], *, full_state: bool) -> tuple[str, ...]:
    base = (str(state["lifecycle"]), str(state["value_band"]))
    return base + (str(state["intent_band"]),) if full_state else base


class HistoricalEvidenceMatcher:
    def __init__(self, *, min_high_support: int = 100, stale_after_days: int = 120) -> None:
        self.min_high_support = min_high_support
        self.stale_after_days = stale_after_days

    def match(
        self,
        records: list[MerchantLearningRecord],
        *,
        state: dict[str, Any],
        action_type: str,
        as_of: datetime,
        full_state: bool,
    ) -> EvidenceMatch:
        requested = state_key(state, full_state=full_state)
        action_records = [
            record
            for record in records
            if record.action_definition.get("action_type") == action_type
        ]
        exact = [
            record
            for record in action_records
            if state_key(record.pre_action_state, full_state=full_state) == requested
        ]
        if not exact:
            return EvidenceMatch(
                HistoricalSupport.OUT_OF_SUPPORT,
                LearnedRecommendation.TEST,
                None,
                None,
                0,
                "No randomized result exists for this state/action.",
            )
        newest = max(record.recorded_at for record in exact)
        if (as_of - newest).days > self.stale_after_days:
            return EvidenceMatch(
                HistoricalSupport.STALE,
                LearnedRecommendation.VERIFY,
                _weighted_effect(exact),
                _combined_interval(exact),
                len(exact),
                "Matching randomized evidence is stale.",
            )
        sample_size = sum(int(record.estimated_effect.get("sample_size", 0)) for record in exact)
        effect = _weighted_effect(exact)
        interval = _combined_interval(exact)
        if sample_size < self.min_high_support:
            return EvidenceMatch(
                HistoricalSupport.PARTIAL_SUPPORT,
                LearnedRecommendation.TEST,
                effect,
                interval,
                len(exact),
                "Matching evidence exists but effective sample support is limited.",
            )
        recommendation = LearnedRecommendation.TEST
        if interval[0] > 0:
            recommendation = LearnedRecommendation.ACT
        elif interval[1] < 0:
            recommendation = LearnedRecommendation.AVOID
        return EvidenceMatch(
            HistoricalSupport.HIGH_SUPPORT,
            recommendation,
            effect,
            interval,
            len(exact),
            "Current randomized evidence supports this state/action.",
        )


def _weighted_effect(records: list[MerchantLearningRecord]) -> float:
    weights = [max(1, int(record.estimated_effect.get("sample_size", 1))) for record in records]
    effects = [float(record.estimated_effect["per_customer"]) for record in records]
    return sum(effect * weight for effect, weight in zip(effects, weights, strict=True)) / sum(
        weights
    )


def _combined_interval(records: list[MerchantLearningRecord]) -> tuple[float, float]:
    standard_errors = [max(float(record.uncertainty.get("se", 1.0)), 1e-9) for record in records]
    inverse_variances = [1 / standard_error**2 for standard_error in standard_errors]
    effects = [float(record.estimated_effect["per_customer"]) for record in records]
    effect = sum(
        estimate * weight for estimate, weight in zip(effects, inverse_variances, strict=True)
    ) / sum(inverse_variances)
    pooled_se = (1 / sum(inverse_variances)) ** 0.5
    return effect - 1.96 * pooled_se, effect + 1.96 * pooled_se
