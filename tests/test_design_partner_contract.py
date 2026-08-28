from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from commercial_twin.merchant_validation.design_partner_contract import (
    MerchantShadowPilotRow,
    MerchantShadowPilotSchema,
    PilotStage,
    PretreatmentFeature,
    ReadOnlyPilotProtocol,
    validate_shadow_pilot,
)

ASSIGNED = datetime(2026, 1, 10, tzinfo=UTC)
MATURE = ASSIGNED + timedelta(days=14)


def _row(unit: str = "customer-1", *, maturity: datetime = MATURE) -> MerchantShadowPilotRow:
    return MerchantShadowPilotRow(
        stable_unit_id=unit,
        assignment_timestamp=ASSIGNED,
        randomized_assignment="EMAIL",
        logged_propensity=0.5,
        eligible=True,
        eligibility_timestamp=ASSIGNED - timedelta(minutes=1),
        pretreatment_features=(
            PretreatmentFeature(
                name="rfm_score", value=3.0, observed_at=ASSIGNED - timedelta(days=1)
            ),
        ),
        purchase_count=1,
        return_count=0,
        gross_purchase_revenue=100.0,
        returns_and_refunds=0.0,
        merchant_funded_discounts=10.0,
        item_level_cogs=40.0,
        fulfillment_cost=5.0,
        payment_fees=3.0,
        campaign_action_cost=0.5,
        contribution_profit=41.5,
        outcome_maturity_timestamp=maturity,
    )


def _schema() -> MerchantShadowPilotSchema:
    return MerchantShadowPilotSchema(
        merchant_id="merchant-1",
        allowed_assignments=("BAU", "EMAIL"),
        assignment_propensities={"BAU": 0.5, "EMAIL": 0.5},
        required_pretreatment_features=("rfm_score",),
    )


def test_valid_mature_extract_reconciles_contribution_profit() -> None:
    report = validate_shadow_pilot((_row(),), _schema(), observed_at=MATURE)
    assert report.passed
    assert report.contribution_profit_total == 41.5
    assert report.autonomous_action_allowed is False


def test_contract_rejects_post_assignment_feature_and_bad_profit() -> None:
    with pytest.raises(ValidationError, match="post-assignment"):
        MerchantShadowPilotRow(
            **{
                **_row().model_dump(),
                "pretreatment_features": (
                    PretreatmentFeature(
                        name="future", value=1, observed_at=ASSIGNED + timedelta(seconds=1)
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="does not reconcile"):
        MerchantShadowPilotRow(**{**_row().model_dump(), "contribution_profit": 99.0})


def test_validation_fails_for_duplicates_or_immature_outcomes() -> None:
    report = validate_shadow_pilot(
        (_row(), _row()), _schema(), observed_at=ASSIGNED + timedelta(days=1)
    )
    assert not report.passed
    assert report.duplicate_unit_ids == ("customer-1",)
    assert report.immature_unit_ids == ("customer-1", "customer-1")
    assert report.contribution_profit_total is None


def test_protocol_is_sequential_preregistered_merchant_approved_and_read_only() -> None:
    protocol = ReadOnlyPilotProtocol()
    protocol = protocol.advance(PilotStage.PREREGISTRATION, occurred_at=ASSIGNED)
    protocol = protocol.advance(
        PilotStage.SHADOW_RECOMMENDATIONS,
        occurred_at=ASSIGNED + timedelta(days=1),
        preregistration_hash="sha256:fixed",
    )
    with pytest.raises(ValueError, match="merchant approval"):
        protocol.advance(
            PilotStage.MERCHANT_APPROVED_RANDOMIZED_TEST,
            occurred_at=ASSIGNED + timedelta(days=2),
        )
    protocol = protocol.advance(
        PilotStage.MERCHANT_APPROVED_RANDOMIZED_TEST,
        occurred_at=ASSIGNED + timedelta(days=2),
        merchant_approved=True,
    )
    protocol = protocol.advance(
        PilotStage.MATURED_CONTRIBUTION_PROFIT_EVALUATION,
        occurred_at=MATURE,
    )
    assert protocol.autonomous_action_allowed is False
    assert protocol.stage is PilotStage.MATURED_CONTRIBUTION_PROFIT_EVALUATION


def test_schema_cannot_enable_autonomous_action() -> None:
    with pytest.raises(ValidationError, match="no autonomous action"):
        MerchantShadowPilotSchema(
            merchant_id="merchant-1",
            allowed_assignments=("BAU", "EMAIL"),
            assignment_propensities={"BAU": 0.5, "EMAIL": 0.5},
            required_pretreatment_features=("rfm_score",),
            autonomous_action_allowed=True,
        )
