"""Preregistered customer-level ITT analysis after the fixed maturity horizon."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import numpy as np
from scipy.stats import chi2, norm

from .contracts import (
    AssignmentRecord,
    DeliveryRecord,
    OutcomeRecord,
    WinbackExperimentContract,
)


@dataclass(frozen=True)
class ArmITTResult:
    arm: str
    control_arm: str
    sample_treatment: int
    sample_control: int
    effect_per_eligible_customer: float
    standard_error: float
    confidence_interval: tuple[float, float]
    total_incremental_cp: float


@dataclass(frozen=True)
class PilotAnalysis:
    experiment_id: str
    status: str
    decision: str
    reason_codes: tuple[str, ...]
    primary_estimand: str
    results: tuple[ArmITTResult, ...]
    srm_p_value: float
    attrition_by_arm: dict[str, float]
    differential_attrition: float
    contamination_rate: float
    currency: str | None
    profit_claim_permitted: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _stratified_difference(
    values: dict[str, float],
    assignments: tuple[AssignmentRecord, ...],
    treatment_arm: str,
    control_arm: str,
    alpha: float,
) -> ArmITTResult:
    strata = sorted({row.stratum for row in assignments})
    total = sum(row.arm in {treatment_arm, control_arm} for row in assignments)
    effect = 0.0
    variance = 0.0
    sample_treatment = 0
    sample_control = 0
    for stratum in strata:
        treated = np.asarray(
            [
                values[row.customer_id]
                for row in assignments
                if row.stratum == stratum and row.arm == treatment_arm
            ]
        )
        control = np.asarray(
            [
                values[row.customer_id]
                for row in assignments
                if row.stratum == stratum and row.arm == control_arm
            ]
        )
        if len(treated) < 2 or len(control) < 2:
            raise ValueError("each analysis stratum needs at least two customers in both arms")
        weight = (len(treated) + len(control)) / total
        effect += weight * float(np.mean(treated) - np.mean(control))
        variance += weight**2 * float(
            np.var(treated, ddof=1) / len(treated) + np.var(control, ddof=1) / len(control)
        )
        sample_treatment += len(treated)
        sample_control += len(control)
    standard_error = float(np.sqrt(variance))
    critical = float(norm.ppf(1 - alpha / 2))
    return ArmITTResult(
        treatment_arm,
        control_arm,
        sample_treatment,
        sample_control,
        effect,
        standard_error,
        (effect - critical * standard_error, effect + critical * standard_error),
        effect * (sample_treatment + sample_control),
    )


def analyze_itt(
    contract: WinbackExperimentContract,
    assignments: tuple[AssignmentRecord, ...],
    outcomes: tuple[OutcomeRecord, ...],
    *,
    analyzed_at: datetime,
    deliveries: tuple[DeliveryRecord, ...] = (),
) -> PilotAnalysis:
    if contract.frozen_at is None or contract.contract_hash is None:
        raise RuntimeError("analysis requires a frozen experiment contract")
    if analyzed_at.tzinfo is None:
        raise ValueError("analyzed_at must be timezone-aware")
    if not assignments:
        raise ValueError("analysis requires immutable assignments")
    maturity = max(row.assigned_at for row in assignments) + timedelta(
        days=contract.outcome_maturity_days
    )
    arm_names = {arm.name for arm in contract.arms}
    counts = {arm: sum(row.arm == arm for row in assignments) for arm in arm_names}
    expected = {
        arm.name: len(assignments) * arm.allocation_probability for arm in contract.arms
    }
    statistic = sum((counts[arm] - expected[arm]) ** 2 / expected[arm] for arm in arm_names)
    srm_p = float(chi2.sf(statistic, df=len(arm_names) - 1))
    reasons: list[str] = []
    if analyzed_at < maturity:
        reasons.append("OUTCOME_NOT_MATURE")
    outcome_map = {row.customer_id: row for row in outcomes}
    if len(outcome_map) != len(outcomes):
        reasons.append("DUPLICATE_OUTCOME")
    if any(row.customer_id not in {item.customer_id for item in assignments} for row in outcomes):
        reasons.append("OUTCOME_WITHOUT_ASSIGNMENT")
    missing_rates = {
        arm: float(
            np.mean(
                [row.customer_id not in outcome_map for row in assignments if row.arm == arm]
            )
        )
        for arm in arm_names
    }
    differential_attrition = max(missing_rates.values()) - min(missing_rates.values())
    if any(rate > 0 for rate in missing_rates.values()):
        reasons.append("MISSING_OUTCOMES")
    if differential_attrition > 0.05:
        reasons.append("DIFFERENTIAL_ATTRITION")
    if srm_p < 0.01:
        reasons.append("SAMPLE_RATIO_MISMATCH")
    currency = next(iter({row.currency for row in outcomes}), None)
    if len({row.currency for row in outcomes}) > 1:
        reasons.append("CURRENCY_MISMATCH")
    values: dict[str, float] = {}
    for customer_id, row in outcome_map.items():
        if row.measured_at < maturity:
            reasons.append("OUTCOME_RECORDED_BEFORE_MATURITY")
        value = row.contribution_profit
        if value is None:
            reasons.append("MISSING_REQUIRED_COST")
        else:
            values[customer_id] = value
    assigned_arm = {row.customer_id: row.arm for row in assignments}
    contaminated = [
        row
        for row in deliveries
        if row.customer_id not in assigned_arm or row.arm != assigned_arm[row.customer_id]
    ]
    contamination_rate = len(contaminated) / max(1, len(deliveries))
    if contamination_rate > 0:
        reasons.append("TREATMENT_CONTAMINATION")
    hard_failures = {
        "OUTCOME_NOT_MATURE",
        "DUPLICATE_OUTCOME",
        "OUTCOME_WITHOUT_ASSIGNMENT",
        "MISSING_OUTCOMES",
        "DIFFERENTIAL_ATTRITION",
        "SAMPLE_RATIO_MISMATCH",
        "CURRENCY_MISMATCH",
        "OUTCOME_RECORDED_BEFORE_MATURITY",
        "MISSING_REQUIRED_COST",
        "TREATMENT_CONTAMINATION",
    }
    if hard_failures.intersection(reasons):
        return PilotAnalysis(
            contract.experiment_id,
            "DATA_NOT_READY",
            "CONTINUE_TESTING",
            tuple(sorted(set(reasons))),
            "CUSTOMER_LEVEL_INTENTION_TO_TREAT",
            (),
            srm_p,
            missing_rates,
            differential_attrition,
            contamination_rate,
            currency,
            False,
        )
    control = next(arm.name for arm in contract.arms if arm.is_control)
    alpha = contract.alpha / (len(contract.arms) - 1)
    results = tuple(
        _stratified_difference(values, assignments, arm.name, control, alpha)
        for arm in contract.arms
        if not arm.is_control
    )
    best = max(results, key=lambda result: result.effect_per_eligible_customer)
    if best.confidence_interval[0] > 0:
        decision = "SCALE"
        reasons.append("MATURE_ITT_LOWER_ABOVE_ZERO")
    elif max(result.confidence_interval[1] for result in results) < 0:
        decision = "STOP"
        reasons.append("MATURE_ITT_UPPER_BELOW_ZERO")
    else:
        decision = "CONTINUE_TESTING"
        reasons.append("MATURE_ITT_INCONCLUSIVE")
    return PilotAnalysis(
        contract.experiment_id,
        "ANALYZED",
        decision,
        tuple(sorted(set(reasons))),
        "CUSTOMER_LEVEL_INTENTION_TO_TREAT",
        results,
        srm_p,
        missing_rates,
        differential_attrition,
        contamination_rate,
        currency,
        True,
    )
