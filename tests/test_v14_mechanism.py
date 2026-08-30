from __future__ import annotations

import pytest

from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.mechanism import (
    ActionLifecycleController,
    CommittedRiskLedger,
    DecisionCard,
    Disposition,
    EvidenceQuality,
    HashDecisionLedger,
    Lifecycle,
    RiskReservation,
    disposition_for,
    maximum_safe_exposure,
)


def _card(identifier: str) -> DecisionCard:
    return DecisionCard(
        decision_id=identifier,
        merchant_id="V14_M01",
        week=1,
        exact_action="EMAIL_REMINDER",
        eligible_population=100,
        timing="week_1",
        bau_forecast=1.0,
        expected_incremental_contribution_profit=0.4,
        total_expected_impact=40.0,
        lower_95=0.1,
        upper_95=0.7,
        probability_beats_bau=0.95,
        evidence_quality=EvidenceQuality(True, True, True, True, True, True, 0.8),
        economic_why="incremental mature contribution profit net of costs",
        primary_risks=("refund_delay",),
        support_limitations=(),
        maximum_safe_exposure=2,
        maturity_week=5,
        disposition=Disposition.DO,
        what_would_change_decision="credible harm or missing mature costs",
    )


def test_v14_disposition_fails_closed_and_separates_test_from_do() -> None:
    assert disposition_for(
        point=1.0,
        lower_95=0.5,
        upper_95=1.5,
        materiality=0.2,
        support_passed=False,
        costs_complete=True,
        data_valid=True,
    ) is Disposition.NOT_ENOUGH_EVIDENCE
    assert disposition_for(
        point=1.0,
        lower_95=-0.1,
        upper_95=2.1,
        materiality=0.2,
        support_passed=True,
        costs_complete=True,
        data_valid=True,
    ) is Disposition.TEST
    assert disposition_for(
        point=1.0,
        lower_95=0.4,
        upper_95=1.6,
        materiality=0.2,
        support_passed=True,
        costs_complete=True,
        data_valid=True,
    ) is Disposition.DO


def test_v14_risk_is_reserved_before_exposure_and_never_released_early() -> None:
    ledger = CommittedRiskLedger(merchant_budget=100.0, action_budget=40.0)
    reservation = RiskReservation("r1", "V14_M01", "EMAIL_REMINDER", 25.0, 1, 5)
    ledger.reserve(reservation)
    assert ledger.open_amount() == 25.0
    with pytest.raises(ValueError, match="before mature"):
        ledger.release("r1", current_week=4)
    ledger.release("r1", current_week=5)
    assert ledger.open_amount() == 0.0


def test_v14_risk_ledgers_enforce_merchant_and_action_budgets() -> None:
    ledger = CommittedRiskLedger(merchant_budget=100.0, action_budget=20.0)
    with pytest.raises(ValueError, match="channel/action"):
        ledger.reserve(RiskReservation("r1", "V14_M01", "SMS_REMINDER", 21.0, 1, 5))


def test_v14_lifecycle_stops_after_mature_harm_and_bounds_reactivation() -> None:
    controller = ActionLifecycleController()
    controller.observe_mature_evidence(week=8, probability_harm=0.97)
    assert controller.state is Lifecycle.PAUSED_HARM
    assert controller.execution_allowed(week=9) is False
    with pytest.raises(ValueError, match="positive mature"):
        controller.request_reactivation(positive_mature_evidence=False, support_passed=True)
    controller.request_reactivation(positive_mature_evidence=True, support_passed=True)
    assert controller.state is Lifecycle.REVALIDATING


def test_v14_hash_ledger_is_append_only_and_tamper_evident() -> None:
    ledger = HashDecisionLedger()
    ledger.append(_card("d1"))
    ledger.append(_card("d2"))
    assert ledger.verify()
    ledger.records[0]["payload"]["week"] = 99
    assert not ledger.verify()


def test_v14_safe_exposure_is_bounded_by_progression_and_risk() -> None:
    assert maximum_safe_exposure(
        eligible_population=10_000,
        credible_downside_per_customer=2.0,
        remaining_risk_budget=100.0,
        matured_batches=0,
    ) == 50
