"""Risk-limited, leased V7 lifecycle with append-only reasoned decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class LifecycleStateV7(StrEnum):
    OBSERVE = "OBSERVE"
    PROBE = "PROBE"
    TEST = "TEST"
    LIMITED_ACTIVE = "LIMITED_ACTIVE"
    ACTIVE = "ACTIVE"
    WATCH = "WATCH"
    PAUSED = "PAUSED"
    REVALIDATING = "REVALIDATING"
    AVOID = "AVOID"


@dataclass(frozen=True)
class LifecycleInput:
    period: int
    support_valid: bool
    viability_positive: bool
    viability_negative: bool
    conservative_enbs_positive: bool
    reservation_accepted: bool
    legitimate_harm_signal: bool
    revalidation_positive: bool
    evidence_expired: bool
    randomized_observations: int
    required_observations: int
    lease_expiry_period: int | None


@dataclass(frozen=True)
class DecisionLedgerRecordV7:
    sequence: int
    previous_state: LifecycleStateV7
    new_state: LifecycleStateV7
    period: int
    reason_code: str
    propensity_required: bool
    risk_reservation_required: bool
    created_at: datetime


class LifecycleControllerV7:
    def __init__(self) -> None:
        self._records: list[DecisionLedgerRecordV7] = []

    @property
    def records(self) -> tuple[DecisionLedgerRecordV7, ...]:
        return tuple(self._records)

    def transition(
        self,
        state: LifecycleStateV7,
        inputs: LifecycleInput,
    ) -> DecisionLedgerRecordV7:
        new = state
        reason = "NO_CHANGE"
        if not inputs.support_valid:
            new, reason = LifecycleStateV7.OBSERVE, "SUPPORT_INSUFFICIENT"
        elif inputs.legitimate_harm_signal:
            new, reason = LifecycleStateV7.PAUSED, "OBSERVABLE_HARM_STOP"
        elif state is LifecycleStateV7.OBSERVE and inputs.conservative_enbs_positive:
            new, reason = LifecycleStateV7.PROBE, "POSITIVE_CONSERVATIVE_ENBS"
        elif state is LifecycleStateV7.PROBE:
            if inputs.conservative_enbs_positive and inputs.reservation_accepted:
                new, reason = LifecycleStateV7.TEST, "FIXED_RANDOMIZED_TEST"
            else:
                new, reason = LifecycleStateV7.OBSERVE, "TEST_NOT_ECONOMIC_OR_UNFUNDED"
        elif state is LifecycleStateV7.TEST:
            if inputs.viability_negative:
                new, reason = LifecycleStateV7.AVOID, "SUPPORTED_NEGATIVE_POLICY_VALUE"
            elif (
                inputs.viability_positive
                and inputs.randomized_observations >= inputs.required_observations
                and inputs.reservation_accepted
            ):
                new, reason = LifecycleStateV7.LIMITED_ACTIVE, "POPULATION_VIABILITY_CONFIRMED"
        elif state is LifecycleStateV7.LIMITED_ACTIVE:
            if inputs.viability_positive and inputs.reservation_accepted:
                new, reason = LifecycleStateV7.ACTIVE, "LEASED_EXPOSURE_EXPANSION"
        elif state is LifecycleStateV7.ACTIVE and (
            inputs.evidence_expired
            or (
                inputs.lease_expiry_period is not None
                and inputs.period >= inputs.lease_expiry_period
            )
        ):
            new, reason = LifecycleStateV7.WATCH, "LEASE_OR_EVIDENCE_EXPIRED"
        elif state is LifecycleStateV7.WATCH:
            new, reason = LifecycleStateV7.PAUSED, "WITHHOLD_PENDING_CONFIRMATION"
        elif state is LifecycleStateV7.PAUSED and inputs.reservation_accepted:
            new, reason = LifecycleStateV7.REVALIDATING, "BOUNDED_REVALIDATION"
        elif state is LifecycleStateV7.REVALIDATING:
            if inputs.revalidation_positive and inputs.reservation_accepted:
                new, reason = LifecycleStateV7.LIMITED_ACTIVE, "SAFE_REACTIVATION"
            elif inputs.viability_negative:
                new, reason = LifecycleStateV7.AVOID, "REVALIDATION_NEGATIVE"
        record = DecisionLedgerRecordV7(
            len(self._records) + 1,
            state,
            new,
            inputs.period,
            reason,
            new in {
                LifecycleStateV7.PROBE,
                LifecycleStateV7.TEST,
                LifecycleStateV7.LIMITED_ACTIVE,
                LifecycleStateV7.ACTIVE,
                LifecycleStateV7.WATCH,
                LifecycleStateV7.REVALIDATING,
            },
            new not in {LifecycleStateV7.OBSERVE, LifecycleStateV7.PAUSED, LifecycleStateV7.AVOID},
            datetime.now(UTC),
        )
        self._records.append(record)
        return record
