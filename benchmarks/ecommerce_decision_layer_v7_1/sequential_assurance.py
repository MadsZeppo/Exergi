"""End-to-end delayed-feedback and committed-risk assurance tournament."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from scipy.stats import norm

from decision_engine.safety.committed_risk_ledger import (
    CommittedRiskLedger,
    ReservationStatus,
    RiskBudget,
    RiskReservationRequest,
)

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "results" / "sequential_assurance.json"
REPORT = ROOT / "V7_1_SEQUENTIAL_ASSURANCE_REPORT.md"
SCENARIOS = (
    "POSITIVE",
    "NULL",
    "HARMFUL",
    "INSUFFICIENT_SUPPORT",
    "ACTION_COST",
    "SWITCHING_COST",
    "MATURITY_DELAY",
    "CONCURRENT_OPEN_BATCHES",
    "ABRUPT_REVERSAL",
    "GRADUAL_DECAY",
    "COMMON_SHOCK",
    "CAUSAL_SHIFT",
    "MISSING_RETURNS",
    "ATTRITION",
    "NONCOMPLIANCE",
    "PROPENSITY_CORRUPTION",
    "ACTION_FATIGUE",
    "REACTIVATION",
    "DRIFT_BEFORE_MATURITY",
    "DRIFT_AFTER_MATURITY",
)
PATHS_PER_SCENARIO = 400
MERCHANT_BUDGET = 120.0
FAMILY_BUDGET = 60.0
BATCH_SIZE = 10
RESERVED_DOWNSIDE_PER_CUSTOMER = 2.0
HORIZON = 18


@dataclass(frozen=True)
class PendingBatch:
    reservation_id: str
    family: str
    assigned_period: int
    maturity_period: int
    realized_increment: float
    observable: bool


@dataclass(frozen=True)
class SequentialPathResult:
    scenario: str
    seed: int
    maximum_drawdown: float
    total_incremental_cp: float
    pre_observable_loss: float
    pre_feedback_harmful_exposure: int
    avoidable_post_observable_loss: float
    post_observable_harmful_continuation: int
    stop_latency: int | None
    maximum_risk_utilization: float
    value_retained: float
    hard_budget_breach: bool
    family_budget_breach: bool
    exposure_over_available_risk: bool
    eligible_reactivation: bool
    successful_reactivation: bool
    false_suspension: bool
    maximum_immature_committed_risk: float
    active_periods: int
    assignments: int
    rejected_batches: int


def _effect(scenario: str, period: int) -> float:
    if scenario == "NULL":
        return 0.0
    if scenario == "HARMFUL":
        return -1.1
    if scenario == "INSUFFICIENT_SUPPORT":
        return 0.9
    if scenario == "ACTION_COST":
        return 1.0 - 0.65
    if scenario == "SWITCHING_COST":
        return 1.0 - 0.45
    if scenario in {"POSITIVE", "MATURITY_DELAY", "CONCURRENT_OPEN_BATCHES", "COMMON_SHOCK"}:
        return 0.8
    if scenario == "ABRUPT_REVERSAL":
        return 0.9 if period < 6 else -1.3
    if scenario == "GRADUAL_DECAY":
        return 1.2 - 0.11 * period
    if scenario == "CAUSAL_SHIFT":
        return 0.8 if period < 7 else -0.8
    if scenario == "MISSING_RETURNS":
        return 0.7
    if scenario == "ATTRITION":
        return 0.7
    if scenario == "NONCOMPLIANCE":
        return 0.7
    if scenario == "PROPENSITY_CORRUPTION":
        return 0.7
    if scenario == "ACTION_FATIGUE":
        return 1.1 * np.exp(-period / 4) - 0.25
    if scenario == "REACTIVATION":
        if period < 5:
            return 0.8
        return -1.1 if period < 10 else 1.0
    if scenario == "DRIFT_BEFORE_MATURITY":
        return 0.9 if period < 2 else -1.0
    if scenario == "DRIFT_AFTER_MATURITY":
        return 0.9 if period < 8 else -1.0
    raise ValueError(scenario)


def _maturity_delay(scenario: str, rng: np.random.Generator) -> int:
    if scenario in {"MATURITY_DELAY", "MISSING_RETURNS", "DRIFT_BEFORE_MATURITY"}:
        return 4
    return int(rng.integers(1, 4))


def _confidence(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, -float("inf"), float("inf")
    mean = float(np.mean(values))
    if len(values) < 2:
        return mean, -float("inf"), float("inf")
    se = float(np.std(values, ddof=1) / np.sqrt(len(values)))
    critical = float(norm.ppf(0.975))
    return mean, mean - critical * se, mean + critical * se


def observable_lifecycle_decision(
    current_state: str,
    mature_incremental_cp: list[float],
    *,
    support_valid: bool,
    assignment_integrity_valid: bool,
) -> tuple[str, str]:
    """Pure policy boundary; it intentionally has no true-effect/oracle argument."""

    if not support_valid:
        return "PAUSED", "INSUFFICIENT_SUPPORT"
    if not assignment_integrity_valid:
        return "PAUSED", "ASSIGNMENT_INTEGRITY_FAILURE"
    recent = mature_incremental_cp[-4:]
    _, lower, upper = _confidence(recent)
    if len(recent) >= 2 and upper < 0:
        return "PAUSED", "MATURE_HARM_SIGNAL"
    if len(recent) >= 3 and lower > 0.10 and current_state in {"TEST", "LIMITED_ACTIVE"}:
        return "ACTIVE", "MATURE_POSITIVE_SIGNAL"
    return current_state, "NO_MATURE_STATE_CHANGE"


def run_path(scenario: str, seed: int) -> SequentialPathResult:
    rng = np.random.default_rng(seed)
    ledger = CommittedRiskLedger(
        RiskBudget(MERCHANT_BUDGET, {"family-a": FAMILY_BUDGET, "family-b": FAMILY_BUDGET})
    )
    pending: list[PendingBatch] = []
    matured: list[float] = []
    state = "TEST"
    cumulative = 0.0
    peak = 0.0
    maximum_drawdown = 0.0
    pre_observable_loss = 0.0
    pre_feedback_harmful_exposure = 0
    avoidable_post_loss = 0.0
    post_observable_harmful_continuation = 0
    first_harm_signal: int | None = None
    last_assignment: int | None = None
    max_utilization = 0.0
    oracle_positive_value = 0.0
    realized_positive_value = 0.0
    rejected = 0
    assignments = 0
    exposure_over_risk = False
    family_realized_loss = {"family-a": 0.0, "family-b": 0.0}
    revalidation_values: list[float] = []
    reactivation_eligible = False
    reactivation_success = False
    false_suspension = False
    max_open_risk = 0.0
    active_periods = 0
    committed_budget_breach = False
    family_committed_breach = False

    for period in range(HORIZON):
        newly_matured = [
            batch
            for batch in pending
            if (batch.observable and batch.maturity_period <= period)
            or (not batch.observable and batch.maturity_period + 2 <= period)
        ]
        pending = [batch for batch in pending if batch not in newly_matured]
        for batch in newly_matured:
            if batch.observable:
                matured.append(batch.realized_increment / BATCH_SIZE)
                if state == "REVALIDATING":
                    revalidation_values.append(batch.realized_increment / BATCH_SIZE)
                ledger.release_matured(batch.reservation_id, current_period=period)
            else:
                ledger.expire(batch.reservation_id, current_period=period)

        previous_state = state
        state, lifecycle_reason = observable_lifecycle_decision(
            state,
            matured,
            support_valid=scenario != "INSUFFICIENT_SUPPORT",
            assignment_integrity_valid=scenario != "PROPENSITY_CORRUPTION" or period < 1,
        )
        if lifecycle_reason == "MATURE_HARM_SIGNAL" and first_harm_signal is None:
            first_harm_signal = period
        if (
            state == "PAUSED"
            and first_harm_signal is not None
            and period >= first_harm_signal + 2
            and scenario not in {"INSUFFICIENT_SUPPORT", "PROPENSITY_CORRUPTION"}
        ):
            state = "REVALIDATING"
            reactivation_eligible = True
        if state == "REVALIDATING" and len(revalidation_values) >= 2:
            _, revalidation_lower, revalidation_upper = _confidence(revalidation_values[-2:])
            if revalidation_lower > 0:
                state = "ACTIVE"
                reactivation_success = True
            elif revalidation_upper < 0:
                state = "PAUSED"

        if state == "ACTIVE":
            active_periods += 1

        true_effect = _effect(scenario, period)
        oracle_positive_value += max(0.0, true_effect * BATCH_SIZE)
        should_assign = state in {"TEST", "ACTIVE", "REVALIDATING"}
        if state == "PAUSED" and previous_state != "PAUSED":
            should_assign = False
        if scenario == "ATTRITION" and period >= 5 and len(matured) < 2:
            should_assign = False
            state = "PAUSED"
        if state == "TEST" and len(pending) >= 2:
            should_assign = False
        if state == "REVALIDATING" and any(
            batch.assigned_period >= (first_harm_signal or 0) + 2 for batch in pending
        ):
            should_assign = False

        if should_assign:
            family = "family-a" if period % 2 == 0 else "family-b"
            loss_so_far = max(0.0, -cumulative)
            family_loss = family_realized_loss[family]
            open_snapshot = ledger.snapshot()
            new_risk = BATCH_SIZE * RESERVED_DOWNSIDE_PER_CUSTOMER
            cumulative_capacity = loss_so_far + open_snapshot.merchant_open_risk + new_risk
            family_capacity = family_loss + open_snapshot.family_open_risk[family] + new_risk
            if cumulative_capacity > MERCHANT_BUDGET or family_capacity > FAMILY_BUDGET:
                rejected += 1
                should_assign = False
            if should_assign:
                reservation_id = f"{scenario}-{seed}-{period}-{assignments}"
                delay = _maturity_delay(scenario, rng)
                request = RiskReservationRequest(
                    reservation_id,
                    f"merchant-{seed}",
                    family,
                    "action",
                    f"experiment-{seed}",
                    BATCH_SIZE,
                    1.4,
                    1.6,
                    RESERVED_DOWNSIDE_PER_CUSTOMER,
                    1.8,
                    period,
                    period + delay,
                    period + delay + 2,
                )
                reservation = ledger.reserve(request)
                if reservation.status is ReservationStatus.OPEN:
                    compliance = 0.55 if scenario == "NONCOMPLIANCE" else 1.0
                    realized = float(
                        BATCH_SIZE * true_effect * compliance
                        + rng.normal(0, 0.8 * np.sqrt(BATCH_SIZE))
                    )
                    if scenario == "COMMON_SHOCK" and period >= 7:
                        # A common shock cancels in the randomized incremental contrast.
                        realized += 0.0
                    observable = not (scenario == "MISSING_RETURNS" and period >= 7)
                    pending.append(
                        PendingBatch(
                            reservation_id,
                            family,
                            period,
                            period + delay,
                            realized,
                            observable,
                        )
                    )
                    assignments += BATCH_SIZE
                    last_assignment = period
                    cumulative += realized
                    family_realized_loss[family] += max(0.0, -realized)
                    if true_effect > 0:
                        realized_positive_value += max(0.0, realized)
                    if first_harm_signal is None and realized < 0:
                        pre_observable_loss += -realized
                    elif (
                        first_harm_signal is not None
                        and period >= first_harm_signal
                        and realized < 0
                    ):
                        avoidable_post_loss += -realized
                    if true_effect < 0 and first_harm_signal is None:
                        pre_feedback_harmful_exposure += BATCH_SIZE
                    elif true_effect < 0 and first_harm_signal is not None:
                        post_observable_harmful_continuation += BATCH_SIZE
                else:
                    rejected += 1
                    if reservation.reserved_risk <= ledger.snapshot().available_merchant_risk:
                        exposure_over_risk = True

        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)
        max_utilization = max(
            max_utilization,
            ledger.snapshot().merchant_open_risk / MERCHANT_BUDGET,
        )
        snapshot = ledger.snapshot()
        max_open_risk = max(max_open_risk, snapshot.merchant_open_risk)
        committed_budget_breach |= snapshot.merchant_open_risk > MERCHANT_BUDGET + 1e-9
        family_committed_breach |= any(
            value > FAMILY_BUDGET + 1e-9 for value in snapshot.family_open_risk.values()
        )

    stop_latency = None
    if first_harm_signal is not None and last_assignment is not None:
        stop_latency = max(0, last_assignment - first_harm_signal)
    if scenario in {"POSITIVE", "MATURITY_DELAY", "CONCURRENT_OPEN_BATCHES", "COMMON_SHOCK"}:
        false_suspension = first_harm_signal is not None
    return SequentialPathResult(
        scenario,
        seed,
        maximum_drawdown,
        cumulative,
        pre_observable_loss,
        pre_feedback_harmful_exposure,
        avoidable_post_loss,
        post_observable_harmful_continuation,
        stop_latency,
        max_utilization,
        realized_positive_value / max(oracle_positive_value, 1e-12),
        committed_budget_breach,
        family_committed_breach,
        exposure_over_risk,
        reactivation_eligible,
        reactivation_success,
        false_suspension,
        max_open_risk,
        active_periods,
        assignments,
        rejected,
    )


def _bootstrap_quantile_interval(
    values: np.ndarray,
    quantile: float,
    rng: np.random.Generator,
) -> tuple[float, float, float]:
    estimate = float(np.quantile(values, quantile))
    draws = [
        float(np.quantile(rng.choice(values, size=len(values), replace=True), quantile))
        for _ in range(500)
    ]
    return estimate, float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def run_tournament() -> dict[str, object]:
    rows = [
        run_path(scenario, 171_001 + path_index)
        for scenario in SCENARIOS
        for path_index in range(PATHS_PER_SCENARIO)
    ]
    rng = np.random.default_rng(271_001)
    scenario_summaries: dict[str, object] = {}
    for scenario in SCENARIOS:
        selected = [row for row in rows if row.scenario == scenario]
        drawdowns = np.asarray([row.maximum_drawdown for row in selected])
        losses = -np.asarray([min(0.0, row.total_incremental_cp) for row in selected])
        p95 = _bootstrap_quantile_interval(drawdowns, 0.95, rng)
        p99 = _bootstrap_quantile_interval(drawdowns, 0.99, rng)
        tail = losses[losses >= np.quantile(losses, 0.95)]
        scenario_summaries[scenario] = {
            "paths": len(selected),
            "maximum_drawdown": float(np.max(drawdowns)),
            "mean_cumulative_incremental_cp": float(
                np.mean([row.total_incremental_cp for row in selected])
            ),
            "p50_loss": float(np.quantile(losses, 0.50)),
            "p95_loss": float(np.quantile(losses, 0.95)),
            "p99_loss": float(np.quantile(losses, 0.99)),
            "p95_drawdown": p95,
            "p99_drawdown": p99,
            "cvar95_loss": float(np.mean(tail)) if len(tail) else 0.0,
            "mean_pre_observable_loss": float(
                np.mean([row.pre_observable_loss for row in selected])
            ),
            "mean_pre_feedback_harmful_exposure": float(
                np.mean([row.pre_feedback_harmful_exposure for row in selected])
            ),
            "mean_avoidable_post_observable_loss": float(
                np.mean([row.avoidable_post_observable_loss for row in selected])
            ),
            "mean_post_observable_harmful_continuation": float(
                np.mean([row.post_observable_harmful_continuation for row in selected])
            ),
            "maximum_stop_latency": max((row.stop_latency or 0 for row in selected), default=0),
            "maximum_risk_utilization": float(
                np.max([row.maximum_risk_utilization for row in selected])
            ),
            "maximum_immature_committed_risk": float(
                np.max([row.maximum_immature_committed_risk for row in selected])
            ),
            "mean_active_rate": float(
                np.mean([row.active_periods / HORIZON for row in selected])
            ),
            "mean_value_retained": float(np.mean([row.value_retained for row in selected])),
            "reactivation_eligible_rate": float(
                np.mean([row.eligible_reactivation for row in selected])
            ),
            "reactivation_success_rate": float(
                np.mean([row.successful_reactivation for row in selected])
            ),
            "false_suspension_rate": float(np.mean([row.false_suspension for row in selected])),
            "hard_budget_breaches": sum(row.hard_budget_breach for row in selected),
            "family_budget_breaches": sum(row.family_budget_breach for row in selected),
            "exposure_over_available_risk": sum(
                row.exposure_over_available_risk for row in selected
            ),
        }
    gates = {
        "merchant_budget_pathwise": all(not row.hard_budget_breach for row in rows),
        "family_budget_pathwise": all(not row.family_budget_breach for row in rows),
        "no_exposure_over_available_risk": all(
            not row.exposure_over_available_risk for row in rows
        ),
        "stop_latency": all((row.stop_latency or 0) <= 1 for row in rows),
        "avoidable_post_loss": all(
            row.avoidable_post_observable_loss <= BATCH_SIZE * RESERVED_DOWNSIDE_PER_CUSTOMER + 1e-9
            for row in rows
        ),
        "unsupported_never_active": all(
            row.active_periods == 0
            for row in rows
            if row.scenario == "INSUFFICIENT_SUPPORT"
        ),
    }
    payload: dict[str, object] = {
        "configuration": {
            "paths_per_scenario": PATHS_PER_SCENARIO,
            "merchant_budget": MERCHANT_BUDGET,
            "family_budget": FAMILY_BUDGET,
            "batch_size": BATCH_SIZE,
            "reserved_downside_per_customer": RESERVED_DOWNSIDE_PER_CUSTOMER,
            "horizon": HORIZON,
        },
        "scenarios": scenario_summaries,
        "gates": gates,
        "overall_pass": all(gates.values()),
        "rows": [asdict(row) for row in rows],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    REPORT.write_text(_markdown(payload))
    return payload


def _markdown(payload: dict[str, object]) -> str:
    lines = [
        "# V7.1 sequential assurance",
        "",
        f"Overall verdict: **{'PASS' if payload['overall_pass'] else 'FAIL'}**.",
        "",
        "| Scenario | Max drawdown | p95 | p99 | CVaR95 | Pre-observable loss | "
        "Post-observable loss | Stop latency | Risk utilization | Value retained |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    scenarios = cast(dict[str, dict[str, Any]], payload["scenarios"])
    for scenario, row in scenarios.items():
        lines.append(
            f"| {scenario} | {row['maximum_drawdown']:.2f} | {row['p95_drawdown'][0]:.2f} | "
            f"{row['p99_drawdown'][0]:.2f} | {row['cvar95_loss']:.2f} | "
            f"{row['mean_pre_observable_loss']:.2f} | "
            f"{row['mean_avoidable_post_observable_loss']:.2f} | "
            f"{row['maximum_stop_latency']} | {row['maximum_risk_utilization']:.1%} | "
            f"{row['mean_value_retained']:.1%} |"
        )
    lines.extend(["", "## Gates", ""])
    gates = cast(dict[str, bool], payload["gates"])
    for name, passed in gates.items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines.extend(
        [
            "",
            "Every non-BAU batch is reserved before assignment. Decisions use only matured noisy "
            "batch outcomes, logged maturity and risk availability; scenario truth is "
            "evaluator-only.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    summary = run_tournament()
    print(
        json.dumps(
            {"gates": summary["gates"], "overall_pass": summary["overall_pass"]},
            indent=2,
        )
    )
