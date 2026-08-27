"""Five deterministic economic-first e-commerce opportunity detectors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from statistics import NormalDist


class EcommerceOpportunityType(StrEnum):
    REPEAT_DETERIORATION = "REPEAT_DETERIORATION"
    HIGH_INTENT_LOW_CONVERSION = "HIGH_INTENT_LOW_CONVERSION"
    DISCOUNT_MARGIN_LEAKAGE = "DISCOUNT_MARGIN_LEAKAGE"
    RETURN_REFUND_LEAKAGE = "RETURN_REFUND_LEAKAGE"
    COHORT_FUNNEL_DETERIORATION = "COHORT_FUNNEL_DETERIORATION"


@dataclass(frozen=True)
class SegmentWindow:
    segment_id: str
    sample_size: int
    baseline_sample_size: int
    persistence_windows: int
    data_quality: str
    current_repeat_rate: float
    baseline_repeat_rate: float
    current_intent_rate: float
    baseline_intent_rate: float
    current_conversion_rate: float
    baseline_conversion_rate: float
    current_discount_share: float
    baseline_discount_share: float
    current_return_rate: float
    baseline_return_rate: float
    current_revenue_per_customer: float
    baseline_revenue_per_customer: float
    current_profit_per_customer: float
    baseline_profit_per_customer: float


@dataclass(frozen=True)
class EcommerceOpportunity:
    opportunity_type: EcommerceOpportunityType
    segment_id: str
    sample_size: int
    current_value: float
    baseline_value: float
    observed_difference: float
    economic_gap: float
    persistence_windows: int
    p_value: float
    q_value: float
    evidence_type: str
    data_quality: str
    why_flagged: str
    priority: float


@dataclass(frozen=True)
class DetectorConfig:
    min_sample: int = 120
    min_persistence: int = 2
    min_economic_gap: float = 500.0
    min_rate_change: float = 0.06
    fdr: float = 0.05


def _proportion_pvalue(current: float, baseline: float, n: int, n0: int) -> float:
    pooled = (current * n + baseline * n0) / (n + n0)
    se = math.sqrt(max(pooled * (1 - pooled) * (1 / n + 1 / n0), 1e-12))
    z_score = abs(current - baseline) / se
    return 2 * (1 - NormalDist().cdf(z_score))


def _bh_qvalues(p_values: list[float]) -> list[float]:
    count = len(p_values)
    order = sorted(range(count), key=p_values.__getitem__)
    result = [1.0] * count
    running = 1.0
    for reverse_rank, index in enumerate(reversed(order), start=1):
        rank = count - reverse_rank + 1
        running = min(running, p_values[index] * count / rank)
        result[index] = min(1.0, running)
    return result


class EcommerceOpportunityEngine:
    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()

    def detect(self, segments: tuple[SegmentWindow, ...]) -> tuple[EcommerceOpportunity, ...]:
        raw: list[tuple[EcommerceOpportunityType, SegmentWindow, float, float, float, str]] = []
        for segment in segments:
            if (
                segment.sample_size < self.config.min_sample
                or segment.baseline_sample_size < self.config.min_sample
                or segment.persistence_windows < self.config.min_persistence
                or segment.data_quality != "PASS"
            ):
                continue
            economic_gap = (
                segment.baseline_profit_per_customer - segment.current_profit_per_customer
            ) * segment.sample_size
            if economic_gap < self.config.min_economic_gap:
                continue
            candidates = self._candidates(segment, economic_gap)
            raw.extend(candidates)
        if not raw:
            return ()
        q_values = _bh_qvalues([item[2] for item in raw])
        opportunities: list[EcommerceOpportunity] = []
        for item, q_value in zip(raw, q_values, strict=True):
            kind, segment, p_value, current, baseline, reason = item
            if q_value > self.config.fdr:
                continue
            gap = (
                segment.baseline_profit_per_customer - segment.current_profit_per_customer
            ) * segment.sample_size
            robustness = max(0.0, 1 - q_value / self.config.fdr)
            opportunities.append(
                EcommerceOpportunity(
                    opportunity_type=kind,
                    segment_id=segment.segment_id,
                    sample_size=segment.sample_size,
                    current_value=current,
                    baseline_value=baseline,
                    observed_difference=current - baseline,
                    economic_gap=gap,
                    persistence_windows=segment.persistence_windows,
                    p_value=p_value,
                    q_value=q_value,
                    evidence_type="DESCRIPTIVE",
                    data_quality=segment.data_quality,
                    why_flagged=reason,
                    priority=gap * robustness,
                )
            )
        return tuple(sorted(opportunities, key=lambda item: item.priority, reverse=True))

    def _candidates(
        self, segment: SegmentWindow, economic_gap: float
    ) -> list[tuple[EcommerceOpportunityType, SegmentWindow, float, float, float, str]]:
        del economic_gap
        result: list[tuple[EcommerceOpportunityType, SegmentWindow, float, float, float, str]] = []
        rate = self.config.min_rate_change
        n, n0 = segment.sample_size, segment.baseline_sample_size
        if segment.baseline_repeat_rate - segment.current_repeat_rate >= rate:
            result.append(
                (
                    EcommerceOpportunityType.REPEAT_DETERIORATION,
                    segment,
                    _proportion_pvalue(
                        segment.current_repeat_rate, segment.baseline_repeat_rate, n, n0
                    ),
                    segment.current_repeat_rate,
                    segment.baseline_repeat_rate,
                    (
                        "Repeat rate deteriorated persistently with an observed "
                        "contribution-profit gap."
                    ),
                )
            )
        if (
            segment.current_intent_rate >= segment.baseline_intent_rate - 0.03
            and segment.baseline_conversion_rate - segment.current_conversion_rate >= rate
        ):
            result.append(
                (
                    EcommerceOpportunityType.HIGH_INTENT_LOW_CONVERSION,
                    segment,
                    _proportion_pvalue(
                        segment.current_conversion_rate,
                        segment.baseline_conversion_rate,
                        n,
                        n0,
                    ),
                    segment.current_conversion_rate,
                    segment.baseline_conversion_rate,
                    "Intent remained supported while purchase conversion deteriorated.",
                )
            )
        if (
            segment.current_revenue_per_customer >= segment.baseline_revenue_per_customer
            and segment.current_discount_share - segment.baseline_discount_share >= rate
        ):
            result.append(
                (
                    EcommerceOpportunityType.DISCOUNT_MARGIN_LEAKAGE,
                    segment,
                    _proportion_pvalue(
                        segment.current_discount_share, segment.baseline_discount_share, n, n0
                    ),
                    segment.current_profit_per_customer,
                    segment.baseline_profit_per_customer,
                    "Revenue held up while discount use and contribution-profit leakage increased.",
                )
            )
        if segment.current_return_rate - segment.baseline_return_rate >= rate:
            result.append(
                (
                    EcommerceOpportunityType.RETURN_REFUND_LEAKAGE,
                    segment,
                    _proportion_pvalue(
                        segment.current_return_rate, segment.baseline_return_rate, n, n0
                    ),
                    segment.current_return_rate,
                    segment.baseline_return_rate,
                    "Returns/refunds created a persistent observed contribution-profit gap.",
                )
            )
        if (
            segment.baseline_conversion_rate - segment.current_conversion_rate >= rate
            and segment.current_intent_rate < segment.baseline_intent_rate - 0.03
        ):
            result.append(
                (
                    EcommerceOpportunityType.COHORT_FUNNEL_DETERIORATION,
                    segment,
                    _proportion_pvalue(
                        segment.current_conversion_rate,
                        segment.baseline_conversion_rate,
                        n,
                        n0,
                    ),
                    segment.current_conversion_rate,
                    segment.baseline_conversion_rate,
                    "The cohort funnel deteriorated against its historical comparison.",
                )
            )
        return result


ACTION_TAXONOMY: dict[EcommerceOpportunityType, tuple[str, ...]] = {
    EcommerceOpportunityType.REPEAT_DETERIORATION: (
        "control",
        "retention_treatment",
        "targeted_offer",
    ),
    EcommerceOpportunityType.HIGH_INTENT_LOW_CONVERSION: (
        "control",
        "free_shipping",
        "targeted_offer",
        "investigate_funnel",
    ),
    EcommerceOpportunityType.DISCOUNT_MARGIN_LEAKAGE: (
        "control",
        "discount_depth_adjustment",
        "bundle_offer",
        "investigate_margin",
    ),
    EcommerceOpportunityType.RETURN_REFUND_LEAKAGE: (
        "control",
        "merchandising_intervention",
        "investigate_returns",
    ),
    EcommerceOpportunityType.COHORT_FUNNEL_DETERIORATION: (
        "control",
        "merchandising_intervention",
        "investigate_funnel",
    ),
}
