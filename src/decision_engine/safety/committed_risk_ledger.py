"""Append-only reservations for all immature non-BAU assigned exposure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class ReservationStatus(StrEnum):
    OPEN = "OPEN"
    RELEASED_MATURED = "RELEASED_MATURED"
    RELEASED_EXPIRED = "RELEASED_EXPIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class RiskBudget:
    merchant_limit: float
    family_limits: dict[str, float]

    def __post_init__(self) -> None:
        if self.merchant_limit < 0 or any(value < 0 for value in self.family_limits.values()):
            raise ValueError("risk budgets cannot be negative")


@dataclass(frozen=True)
class RiskReservationRequest:
    reservation_id: str
    merchant_id: str
    action_family: str
    action: str
    experiment_id: str
    assigned_units: int
    posterior_credible_downside: float
    empirical_family_downside_floor: float
    merchant_worst_case_downside: float
    shift_stress_downside: float
    assigned_at_period: int
    outcome_maturity_period: int
    conservative_expiry_period: int


@dataclass(frozen=True)
class RiskReservation:
    request: RiskReservationRequest
    downside_per_unit: float
    reserved_risk: float
    status: ReservationStatus
    recorded_at: datetime
    released_at_period: int | None = None
    reason: str = ""


@dataclass(frozen=True)
class RiskLedgerSnapshot:
    merchant_open_risk: float
    family_open_risk: dict[str, float]
    available_merchant_risk: float
    available_family_risk: dict[str, float]
    open_reservations: int


class CommittedRiskLedger:
    def __init__(self, budget: RiskBudget) -> None:
        self.budget = budget
        self._latest: dict[str, RiskReservation] = {}
        self._events: list[RiskReservation] = []

    @property
    def events(self) -> tuple[RiskReservation, ...]:
        return tuple(self._events)

    def snapshot(self) -> RiskLedgerSnapshot:
        opened = [item for item in self._latest.values() if item.status is ReservationStatus.OPEN]
        merchant = float(sum(item.reserved_risk for item in opened))
        families = {
            family: float(
                sum(item.reserved_risk for item in opened if item.request.action_family == family)
            )
            for family in self.budget.family_limits
        }
        return RiskLedgerSnapshot(
            merchant,
            families,
            max(0.0, self.budget.merchant_limit - merchant),
            {
                family: max(0.0, limit - families.get(family, 0.0))
                for family, limit in self.budget.family_limits.items()
            },
            len(opened),
        )

    def reserve(self, request: RiskReservationRequest) -> RiskReservation:
        if request.reservation_id in self._latest:
            raise ValueError("reservation IDs are immutable and unique")
        if request.assigned_units <= 0:
            raise ValueError("all non-BAU reservations require positive assigned units")
        if request.outcome_maturity_period <= request.assigned_at_period:
            raise ValueError("risk cannot mature before or at assignment")
        if request.conservative_expiry_period < request.outcome_maturity_period:
            raise ValueError("conservative expiry cannot precede expected outcome maturity")
        downside_inputs = (
            request.posterior_credible_downside,
            request.empirical_family_downside_floor,
            request.merchant_worst_case_downside,
            request.shift_stress_downside,
        )
        if any(value < 0 for value in downside_inputs):
            raise ValueError("downside inputs must be non-negative losses")
        downside = max(downside_inputs)
        reserved = request.assigned_units * downside
        snapshot = self.snapshot()
        family_available = snapshot.available_family_risk.get(request.action_family, 0.0)
        accepted = (
            reserved <= snapshot.available_merchant_risk + 1e-12
            and reserved <= family_available + 1e-12
        )
        item = RiskReservation(
            request,
            downside,
            reserved,
            ReservationStatus.OPEN if accepted else ReservationStatus.REJECTED,
            datetime.now(UTC),
            reason=("risk reserved until maturity" if accepted else "hard risk budget exceeded"),
        )
        self._latest[request.reservation_id] = item
        self._events.append(item)
        return item

    def release_matured(self, reservation_id: str, *, current_period: int) -> RiskReservation:
        item = self._latest[reservation_id]
        if item.status is not ReservationStatus.OPEN:
            raise ValueError("only an open reservation can be released")
        if current_period < item.request.outcome_maturity_period:
            raise ValueError("reservation cannot be released before outcome maturity")
        released = RiskReservation(
            item.request,
            item.downside_per_unit,
            item.reserved_risk,
            ReservationStatus.RELEASED_MATURED,
            datetime.now(UTC),
            current_period,
            "corresponding outcome matured",
        )
        self._latest[reservation_id] = released
        self._events.append(released)
        return released

    def expire(self, reservation_id: str, *, current_period: int) -> RiskReservation:
        item = self._latest[reservation_id]
        if item.status is not ReservationStatus.OPEN:
            raise ValueError("only an open reservation can expire")
        if current_period < item.request.conservative_expiry_period:
            raise ValueError("reservation cannot expire before conservative expiry")
        released = RiskReservation(
            item.request,
            item.downside_per_unit,
            item.reserved_risk,
            ReservationStatus.RELEASED_EXPIRED,
            datetime.now(UTC),
            current_period,
            "conservative expiry reached without a mature outcome",
        )
        self._latest[reservation_id] = released
        self._events.append(released)
        return released
