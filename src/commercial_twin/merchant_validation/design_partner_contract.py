"""Fail-closed data contract for a read-only merchant shadow pilot."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class PretreatmentFeature(_Frozen):
    name: str = Field(min_length=1)
    value: str | int | float | bool
    observed_at: datetime

    @model_validator(mode="after")
    def require_aware_timestamp(self) -> PretreatmentFeature:
        if self.observed_at.tzinfo is None:
            raise ValueError("pretreatment feature timestamp must be timezone-aware")
        return self


class MerchantShadowPilotRow(_Frozen):
    """One immutable randomized unit with a matured economic outcome."""

    stable_unit_id: str = Field(min_length=1)
    assignment_timestamp: datetime
    randomized_assignment: str = Field(min_length=1)
    logged_propensity: float = Field(gt=0, le=1)
    eligible: bool
    eligibility_timestamp: datetime
    pretreatment_features: tuple[PretreatmentFeature, ...]
    purchase_count: int = Field(ge=0)
    return_count: int = Field(ge=0)
    gross_purchase_revenue: float = Field(ge=0)
    returns_and_refunds: float = Field(ge=0)
    merchant_funded_discounts: float = Field(ge=0)
    item_level_cogs: float = Field(ge=0)
    fulfillment_cost: float = Field(ge=0)
    payment_fees: float = Field(ge=0)
    campaign_action_cost: float = Field(ge=0)
    contribution_profit: float
    outcome_maturity_timestamp: datetime

    @model_validator(mode="after")
    def validate_row(self) -> MerchantShadowPilotRow:
        timestamps = (
            self.assignment_timestamp,
            self.eligibility_timestamp,
            self.outcome_maturity_timestamp,
        )
        if any(value.tzinfo is None for value in timestamps):
            raise ValueError("all pilot timestamps must be timezone-aware")
        if self.eligibility_timestamp > self.assignment_timestamp:
            raise ValueError("eligibility must be frozen no later than assignment")
        if self.outcome_maturity_timestamp <= self.assignment_timestamp:
            raise ValueError("outcome maturity must occur after assignment")
        if not self.eligible:
            raise ValueError("ineligible units cannot enter the randomized evaluation table")
        names = [feature.name for feature in self.pretreatment_features]
        if len(names) != len(set(names)):
            raise ValueError("pretreatment feature names must be unique per unit")
        if any(
            feature.observed_at > self.assignment_timestamp
            for feature in self.pretreatment_features
        ):
            raise ValueError("post-assignment feature timestamp is forbidden")
        calculated = (
            self.gross_purchase_revenue
            - self.returns_and_refunds
            - self.merchant_funded_discounts
            - self.item_level_cogs
            - self.fulfillment_cost
            - self.payment_fees
            - self.campaign_action_cost
        )
        if abs(calculated - self.contribution_profit) > 1e-6:
            raise ValueError("declared contribution profit does not reconcile to the cost ledger")
        return self

    def mature_contribution_profit(self, *, observed_at: datetime) -> float | None:
        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if observed_at < self.outcome_maturity_timestamp:
            return None
        return self.contribution_profit


class MerchantShadowPilotSchema(_Frozen):
    schema_version: str = "1.0"
    merchant_id: str = Field(min_length=1)
    randomization_unit: str = "customer"
    allowed_assignments: tuple[str, ...]
    assignment_propensities: dict[str, float]
    required_pretreatment_features: tuple[str, ...]
    primary_outcome: str = "contribution_profit"
    read_only: bool = True
    autonomous_action_allowed: bool = False

    @model_validator(mode="after")
    def validate_schema(self) -> MerchantShadowPilotSchema:
        if len(self.allowed_assignments) < 2 or len(set(self.allowed_assignments)) != len(
            self.allowed_assignments
        ):
            raise ValueError("at least two unique randomized assignments are required")
        if set(self.assignment_propensities) != set(self.allowed_assignments):
            raise ValueError("every assignment requires one declared propensity")
        probabilities = tuple(self.assignment_propensities.values())
        if any(value <= 0 or value > 1 for value in probabilities):
            raise ValueError("assignment propensities must be in (0, 1]")
        if abs(sum(probabilities) - 1.0) > 1e-9:
            raise ValueError("assignment propensities must sum to one")
        if len(set(self.required_pretreatment_features)) != len(
            self.required_pretreatment_features
        ):
            raise ValueError("required pretreatment features must be unique")
        if not self.read_only or self.autonomous_action_allowed:
            raise ValueError("V1 merchant pilot must remain read-only with no autonomous action")
        return self


class MerchantPilotValidationReport(_Frozen):
    passed: bool
    row_count: int
    mature_row_count: int
    duplicate_unit_ids: tuple[str, ...]
    invalid_assignments: tuple[str, ...]
    propensity_mismatches: tuple[str, ...]
    missing_pretreatment_features: dict[str, tuple[str, ...]]
    immature_unit_ids: tuple[str, ...]
    contribution_profit_total: float | None
    autonomous_action_allowed: bool = False


def validate_shadow_pilot(
    rows: tuple[MerchantShadowPilotRow, ...],
    schema: MerchantShadowPilotSchema,
    *,
    observed_at: datetime,
) -> MerchantPilotValidationReport:
    """Validate one frozen pilot extract without executing or mutating merchant actions."""

    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    ids = [row.stable_unit_id for row in rows]
    duplicates = tuple(sorted({unit for unit in ids if ids.count(unit) > 1}))
    invalid_assignments = tuple(
        sorted(
            row.stable_unit_id
            for row in rows
            if row.randomized_assignment not in schema.allowed_assignments
        )
    )
    propensity_mismatches = tuple(
        sorted(
            row.stable_unit_id
            for row in rows
            if row.randomized_assignment in schema.assignment_propensities
            and abs(
                row.logged_propensity - schema.assignment_propensities[row.randomized_assignment]
            )
            > 1e-9
        )
    )
    required = set(schema.required_pretreatment_features)
    missing = {
        row.stable_unit_id: tuple(
            sorted(required - {feature.name for feature in row.pretreatment_features})
        )
        for row in rows
        if required - {feature.name for feature in row.pretreatment_features}
    }
    immature = tuple(
        sorted(row.stable_unit_id for row in rows if observed_at < row.outcome_maturity_timestamp)
    )
    passed = not (duplicates or invalid_assignments or propensity_mismatches or missing or immature)
    total = sum(row.contribution_profit for row in rows) if passed else None
    return MerchantPilotValidationReport(
        passed=passed,
        row_count=len(rows),
        mature_row_count=len(rows) - len(immature),
        duplicate_unit_ids=duplicates,
        invalid_assignments=invalid_assignments,
        propensity_mismatches=propensity_mismatches,
        missing_pretreatment_features=missing,
        immature_unit_ids=immature,
        contribution_profit_total=total,
    )


class PilotStage(StrEnum):
    HISTORICAL_AUDIT = "HISTORICAL_AUDIT"
    PREREGISTRATION = "PREREGISTRATION"
    SHADOW_RECOMMENDATIONS = "SHADOW_RECOMMENDATIONS"
    MERCHANT_APPROVED_RANDOMIZED_TEST = "MERCHANT_APPROVED_RANDOMIZED_TEST"
    MATURED_CONTRIBUTION_PROFIT_EVALUATION = "MATURED_CONTRIBUTION_PROFIT_EVALUATION"


_STAGE_ORDER = tuple(PilotStage)


class ReadOnlyPilotProtocol(_Frozen):
    stage: PilotStage = PilotStage.HISTORICAL_AUDIT
    merchant_approval_timestamp: datetime | None = None
    preregistration_hash: str | None = None
    autonomous_action_allowed: bool = False
    audit_log: tuple[dict[str, Any], ...] = ()

    @model_validator(mode="after")
    def enforce_read_only(self) -> ReadOnlyPilotProtocol:
        if self.autonomous_action_allowed:
            raise ValueError("autonomous merchant action is forbidden")
        if (
            self.merchant_approval_timestamp is not None
            and self.merchant_approval_timestamp.tzinfo is None
        ):
            raise ValueError("merchant approval timestamp must be timezone-aware")
        return self

    def advance(
        self,
        next_stage: PilotStage,
        *,
        occurred_at: datetime,
        merchant_approved: bool = False,
        preregistration_hash: str | None = None,
    ) -> ReadOnlyPilotProtocol:
        if occurred_at.tzinfo is None:
            raise ValueError("protocol timestamp must be timezone-aware")
        current_index, next_index = _STAGE_ORDER.index(self.stage), _STAGE_ORDER.index(next_stage)
        if next_index != current_index + 1:
            raise ValueError("pilot stages must advance exactly one step in the fixed order")
        frozen_hash = preregistration_hash or self.preregistration_hash
        if next_index >= _STAGE_ORDER.index(PilotStage.SHADOW_RECOMMENDATIONS) and not frozen_hash:
            raise ValueError("preregistration hash is required before shadow recommendations")
        approval = self.merchant_approval_timestamp
        if next_stage is PilotStage.MERCHANT_APPROVED_RANDOMIZED_TEST:
            if not merchant_approved:
                raise ValueError("explicit merchant approval is required before randomization")
            approval = occurred_at
        entry = {
            "from": self.stage.value,
            "to": next_stage.value,
            "occurred_at": occurred_at.isoformat(),
            "merchant_approved": merchant_approved,
        }
        return ReadOnlyPilotProtocol(
            stage=next_stage,
            merchant_approval_timestamp=approval,
            preregistration_hash=frozen_hash,
            audit_log=(*self.audit_log, entry),
        )
