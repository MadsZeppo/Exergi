from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Disposition(StrEnum):
    DO = "DO"
    TEST = "TEST"
    AVOID = "AVOID"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"


class Lifecycle(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED_HARM = "PAUSED_HARM"
    REVALIDATING = "REVALIDATING"
    EXHAUSTED = "EXHAUSTED"


@dataclass(frozen=True)
class EvidenceQuality:
    randomized: bool
    known_propensity: bool
    support_passed: bool
    costs_complete: bool
    point_in_time_passed: bool
    placebo_passed: bool
    fold_stability: float


@dataclass(frozen=True)
class DecisionCard:
    decision_id: str
    merchant_id: str
    week: int
    exact_action: str
    eligible_population: int
    timing: str
    bau_forecast: float
    expected_incremental_contribution_profit: float
    total_expected_impact: float
    lower_95: float
    upper_95: float
    probability_beats_bau: float
    evidence_quality: EvidenceQuality
    economic_why: str
    primary_risks: tuple[str, ...]
    support_limitations: tuple[str, ...]
    maximum_safe_exposure: int
    maturity_week: int
    disposition: Disposition
    what_would_change_decision: str


@dataclass(frozen=True)
class RiskReservation:
    reservation_id: str
    merchant_id: str
    action: str
    amount: float
    created_week: int
    maturity_week: int
    released_week: int | None = None


class CommittedRiskLedger:
    def __init__(self, merchant_budget: float, action_budget: float) -> None:
        if merchant_budget <= 0 or action_budget <= 0:
            raise ValueError("risk budgets must be positive")
        self.merchant_budget = merchant_budget
        self.action_budget = action_budget
        self._reservations: dict[str, RiskReservation] = {}

    def open_amount(self, *, action: str | None = None) -> float:
        values = (
            item
            for item in self._reservations.values()
            if item.released_week is None and (action is None or item.action == action)
        )
        return float(sum(item.amount for item in values))

    def reserve(self, reservation: RiskReservation) -> None:
        if reservation.reservation_id in self._reservations:
            raise ValueError("duplicate risk reservation")
        if reservation.released_week is not None:
            raise ValueError("new reservation cannot already be released")
        if self.open_amount() + reservation.amount > self.merchant_budget + 1e-9:
            raise ValueError("merchant risk budget exceeded")
        action_total = self.open_amount(action=reservation.action) + reservation.amount
        if action_total > self.action_budget + 1e-9:
            raise ValueError("channel/action risk budget exceeded")
        self._reservations[reservation.reservation_id] = reservation

    def release(self, reservation_id: str, *, current_week: int) -> None:
        reservation = self._reservations.get(reservation_id)
        if reservation is None or reservation.released_week is not None:
            raise ValueError("risk reservation missing or already released")
        if current_week < reservation.maturity_week:
            raise ValueError("risk cannot be released before mature economic outcome")
        self._reservations[reservation_id] = RiskReservation(
            **{**asdict(reservation), "released_week": current_week}
        )


class ActionLifecycleController:
    def __init__(self) -> None:
        self.state = Lifecycle.ACTIVE
        self.revalidations = 0
        self.harm_observed_week: int | None = None

    def observe_mature_evidence(self, *, week: int, probability_harm: float) -> None:
        if probability_harm >= 0.95:
            self.state = Lifecycle.PAUSED_HARM
            self.harm_observed_week = week

    def request_reactivation(self, *, positive_mature_evidence: bool, support_passed: bool) -> None:
        if self.state is not Lifecycle.PAUSED_HARM:
            raise ValueError("only a harm-paused action can revalidate")
        if self.revalidations >= 1:
            self.state = Lifecycle.EXHAUSTED
            return
        if not positive_mature_evidence or not support_passed:
            raise ValueError("reactivation requires positive mature evidence and support")
        self.revalidations += 1
        self.state = Lifecycle.REVALIDATING

    def execution_allowed(self, *, week: int) -> bool:
        if self.state is Lifecycle.PAUSED_HARM and self.harm_observed_week is not None:
            return week <= self.harm_observed_week
        return self.state in {Lifecycle.ACTIVE, Lifecycle.REVALIDATING}


class HashDecisionLedger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, card: DecisionCard) -> str:
        payload = asdict(card)
        previous_hash = self.records[-1]["record_hash"] if self.records else "GENESIS"
        encoded = json.dumps(
            {"payload": payload, "previous_hash": previous_hash},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        record_hash = hashlib.sha256(encoded).hexdigest()
        self.records.append(
            {"payload": payload, "previous_hash": previous_hash, "record_hash": record_hash}
        )
        return record_hash

    def verify(self) -> bool:
        previous_hash = "GENESIS"
        for record in self.records:
            encoded = json.dumps(
                {"payload": record["payload"], "previous_hash": previous_hash},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            if record["previous_hash"] != previous_hash:
                return False
            if record["record_hash"] != hashlib.sha256(encoded).hexdigest():
                return False
            previous_hash = record["record_hash"]
        return True


def disposition_for(
    *,
    point: float,
    lower_95: float,
    upper_95: float,
    materiality: float,
    support_passed: bool,
    costs_complete: bool,
    data_valid: bool,
) -> Disposition:
    if not support_passed or not costs_complete or not data_valid:
        return Disposition.NOT_ENOUGH_EVIDENCE
    if upper_95 < -materiality:
        return Disposition.AVOID
    if lower_95 > materiality:
        return Disposition.DO
    if point > materiality:
        return Disposition.TEST
    return Disposition.NOT_ENOUGH_EVIDENCE


def maximum_safe_exposure(
    *,
    eligible_population: int,
    credible_downside_per_customer: float,
    remaining_risk_budget: float,
    matured_batches: int,
) -> int:
    progressive_fraction = 0.02 if matured_batches < 1 else 0.05
    progressive_cap = int(eligible_population * progressive_fraction)
    risk_cap = int(remaining_risk_budget / max(credible_downside_per_customer, 0.01))
    return max(0, min(progressive_cap, risk_cap))
