"""Observable-only V7.2 lifecycle with immediate harm latch and evidence leases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LifecycleState(StrEnum):
    TEST = "TEST"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    REVALIDATING = "REVALIDATING"


@dataclass(frozen=True)
class EvidenceBatch:
    batch_id: str
    observed_period: int
    estimate: float
    standard_error: float
    randomized: bool = True
    mature: bool = True
    support_valid: bool = True

    @property
    def lower_95(self) -> float:
        return self.estimate - 1.959963984540054 * self.standard_error

    @property
    def upper_95(self) -> float:
        return self.estimate + 1.959963984540054 * self.standard_error


@dataclass(frozen=True)
class SequentialControllerConfig:
    materiality: float = 0.10
    freshness_periods: int = 4
    cooldown_periods: int = 2
    positive_batches_to_activate: int = 2
    harm_point_threshold: float = -0.10


@dataclass(frozen=True)
class LifecycleDecision:
    state: LifecycleState
    allow_new_exposure: bool
    allow_revalidation_batch: bool
    reason_code: str
    harm_latched: bool


class SequentialController:
    """Pure controller: identical observable history always gives the same decision."""

    def __init__(self, config: SequentialControllerConfig | None = None) -> None:
        self.config = config or SequentialControllerConfig()

    def decide(
        self,
        *,
        current_state: LifecycleState,
        current_period: int,
        mature_evidence: tuple[EvidenceBatch, ...],
        support_valid: bool,
        assignment_integrity_valid: bool,
        last_pause_period: int | None = None,
    ) -> LifecycleDecision:
        valid = tuple(
            row
            for row in mature_evidence
            if row.mature
            and row.randomized
            and row.support_valid
            and row.observed_period <= current_period
        )
        if not support_valid:
            return LifecycleDecision(
                LifecycleState.PAUSED, False, False, "INSUFFICIENT_SUPPORT", False
            )
        if not assignment_integrity_valid:
            return LifecycleDecision(
                LifecycleState.PAUSED, False, False, "ASSIGNMENT_INTEGRITY_FAILURE", False
            )
        harm_window = tuple(
            row
            for row in valid
            if last_pause_period is None
            or current_state in {LifecycleState.TEST, LifecycleState.ACTIVE}
            or row.observed_period > last_pause_period
        )
        credible_harm = any(
            row.upper_95 < 0
            or (
                row.estimate <= self.config.harm_point_threshold
                and row.standard_error == 0
            )
            for row in harm_window
        )
        if credible_harm:
            return LifecycleDecision(
                LifecycleState.PAUSED, False, False, "IMMEDIATE_MATURE_HARM_LATCH", True
            )
        latest = max((row.observed_period for row in valid), default=None)
        if current_state is LifecycleState.ACTIVE and (
            latest is None or current_period - latest > self.config.freshness_periods
        ):
            return LifecycleDecision(
                LifecycleState.REVALIDATING, False, True, "EVIDENCE_LEASE_EXPIRED", False
            )
        if current_state is LifecycleState.PAUSED:
            cooled = last_pause_period is not None and (
                current_period - last_pause_period >= self.config.cooldown_periods
            )
            return LifecycleDecision(
                LifecycleState.REVALIDATING if cooled else LifecycleState.PAUSED,
                False,
                cooled,
                "COOLDOWN_COMPLETE_REVALIDATE" if cooled else "HARM_COOLDOWN",
                False,
            )
        recent_positive = [
            row
            for row in valid
            if latest is not None
            and latest - row.observed_period <= self.config.freshness_periods
            and (last_pause_period is None or row.observed_period > last_pause_period)
            and row.lower_95 > self.config.materiality
        ]
        if len(recent_positive) >= self.config.positive_batches_to_activate:
            return LifecycleDecision(
                LifecycleState.ACTIVE, True, False, "FRESH_RANDOMIZED_POSITIVE_EVIDENCE", False
            )
        return LifecycleDecision(
            current_state,
            current_state is LifecycleState.TEST,
            current_state is LifecycleState.REVALIDATING,
            "AWAITING_MATURE_EVIDENCE",
            False,
        )
