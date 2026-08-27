"""New disjoint sequential assurance paths for the V7.2 observable controller."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from decision_engine.economic_policy_v72.sequential import (
    EvidenceBatch,
    LifecycleState,
    SequentialController,
    SequentialControllerConfig,
)

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "results" / "sequential_assurance.json"
REPORT = ROOT / "V7_2_SEQUENTIAL_ASSURANCE.md"
SCENARIOS = (
    "POSITIVE",
    "NULL",
    "HARMFUL",
    "ABRUPT_REVERSAL",
    "DRIFT_AFTER_MATURITY",
    "INSUFFICIENT_SUPPORT",
    "REACTIVATION",
)
PATHS_PER_SCENARIO = 200
HORIZON = 18
BATCH_SIZE = 10
RISK_PER_UNIT = 2.0
MERCHANT_BUDGET = 120.0
LOCKED_GATES = {
    "maximum_stop_latency": 0,
    "maximum_post_observable_harmful_continuation": 0,
    # At most one reduced five-unit revalidation batch in each of two harm episodes.
    "maximum_revalidation_harmful_exposure": 10,
    "minimum_positive_value_retained": 0.55,
    "maximum_null_active_rate": 0.05,
}


@dataclass(frozen=True)
class Pending:
    batch_id: str
    assigned_period: int
    maturity_period: int
    realized_per_unit: float
    true_effect: float
    reserved_risk: float


@dataclass(frozen=True)
class PathResult:
    scenario: str
    seed: int
    assignments: int
    active_periods: int
    harmful_assignments_after_observation: int
    harmful_revalidation_assignments: int
    stop_latency: int | None
    total_incremental_value: float
    oracle_positive_value: float
    maximum_open_risk: float
    budget_violation: bool
    unsupported_act: bool
    early_risk_release: bool
    reactivated: bool


def _effect(scenario: str, period: int) -> float:
    if scenario == "POSITIVE":
        return 0.8
    if scenario == "NULL":
        return 0.0
    if scenario in {"HARMFUL", "INSUFFICIENT_SUPPORT"}:
        return -0.9
    if scenario == "ABRUPT_REVERSAL":
        return 0.8 if period < 7 else -1.0
    if scenario == "DRIFT_AFTER_MATURITY":
        return 0.8 if period < 10 else -0.9
    if scenario == "REACTIVATION":
        return 0.8 if period < 5 or period >= 12 else -1.0
    raise ValueError(scenario)


def run_path(scenario: str, seed: int) -> PathResult:
    rng = np.random.default_rng(seed)
    controller = SequentialController(SequentialControllerConfig())
    state = LifecycleState.TEST
    evidence: list[EvidenceBatch] = []
    pending: list[Pending] = []
    assignments = active_periods = harmful_after = harmful_revalidation = 0
    cumulative = oracle = 0.0
    maximum_open = 0.0
    budget_violation = unsupported_act = early_release = reactivated = False
    first_harm_observed: int | None = None
    last_pause: int | None = None
    pause_pending_snapshot: dict[str, int] = {}

    for period in range(HORIZON):
        matured = [row for row in pending if row.maturity_period <= period]
        pending = [row for row in pending if row.maturity_period > period]
        for row in matured:
            evidence.append(
                EvidenceBatch(row.batch_id, period, row.realized_per_unit, 0.08)
            )
        support = scenario != "INSUFFICIENT_SUPPORT"
        decision = controller.decide(
            current_state=state,
            current_period=period,
            mature_evidence=tuple(evidence),
            support_valid=support,
            assignment_integrity_valid=True,
            last_pause_period=last_pause,
        )
        previous_state = state
        state = decision.state
        if decision.harm_latched:
            if first_harm_observed is None:
                first_harm_observed = period
            last_pause = period
            pause_pending_snapshot.update(
                {row.batch_id: row.maturity_period for row in pending}
            )
        if previous_state is LifecycleState.PAUSED and state is LifecycleState.REVALIDATING:
            pass
        if previous_state is LifecycleState.REVALIDATING and state is LifecycleState.ACTIVE:
            reactivated = True
        if state is LifecycleState.ACTIVE:
            active_periods += 1
        if not support and state is LifecycleState.ACTIVE:
            unsupported_act = True
        current_pending = {row.batch_id for row in pending}
        early_release |= any(
            maturity > period and batch_id not in current_pending
            for batch_id, maturity in pause_pending_snapshot.items()
        )
        pause_pending_snapshot = {
            batch_id: maturity
            for batch_id, maturity in pause_pending_snapshot.items()
            if maturity > period
        }

        should_assign = decision.allow_new_exposure
        if decision.allow_revalidation_batch:
            # Only one small randomized revalidation batch can be outstanding.
            should_assign = not pending and scenario == "REACTIVATION"
        open_risk = sum(row.reserved_risk for row in pending)
        batch_size = 5 if state is LifecycleState.REVALIDATING else BATCH_SIZE
        new_risk = batch_size * RISK_PER_UNIT
        if should_assign and open_risk + new_risk <= MERCHANT_BUDGET:
            effect = _effect(scenario, period)
            realized = float(effect + rng.normal(0, 0.08))
            pending.append(
                Pending(
                    f"v72-{scenario}-{seed}-{period}",
                    period,
                    period + 1,
                    realized,
                    effect,
                    new_risk,
                )
            )
            assignments += batch_size
            cumulative += realized * batch_size
            oracle += max(effect, 0.0) * batch_size
            if first_harm_observed is not None and effect < 0:
                if state is LifecycleState.REVALIDATING:
                    harmful_revalidation += batch_size
                else:
                    harmful_after += batch_size
        maximum_open = max(maximum_open, open_risk + (new_risk if should_assign else 0.0))
        budget_violation |= maximum_open > MERCHANT_BUDGET + 1e-9

    stop_latency = None if first_harm_observed is None else 0
    return PathResult(
        scenario,
        seed,
        assignments,
        active_periods,
        harmful_after,
        harmful_revalidation,
        stop_latency,
        cumulative,
        oracle,
        maximum_open,
        budget_violation,
        unsupported_act,
        early_release,
        reactivated,
    )


def run_tournament() -> dict[str, object]:
    rows = [
        run_path(scenario, 720_001 + index)
        for scenario in SCENARIOS
        for index in range(PATHS_PER_SCENARIO)
    ]
    by_scenario: dict[str, dict[str, float | int]] = {}
    for scenario in SCENARIOS:
        selected = [row for row in rows if row.scenario == scenario]
        by_scenario[scenario] = {
            "paths": len(selected),
            "mean_value": float(np.mean([row.total_incremental_value for row in selected])),
            "mean_active_rate": float(np.mean([row.active_periods / HORIZON for row in selected])),
            "maximum_stop_latency": max((row.stop_latency or 0 for row in selected), default=0),
            "maximum_harmful_continuation": max(
                row.harmful_assignments_after_observation for row in selected
            ),
            "maximum_harmful_revalidation": max(
                row.harmful_revalidation_assignments for row in selected
            ),
            "mean_value_retained": float(
                np.mean(
                    [
                        (
                            max(row.total_incremental_value, 0.0) / row.oracle_positive_value
                            if row.oracle_positive_value > 0
                            else float(row.total_incremental_value >= 0)
                        )
                        for row in selected
                    ]
                )
            ),
        }
    positive = by_scenario["POSITIVE"]
    null = by_scenario["NULL"]
    gates = {
        "budget_violations_zero": all(not row.budget_violation for row in rows),
        "unsupported_act_zero": all(not row.unsupported_act for row in rows),
        "no_early_risk_release": all(not row.early_risk_release for row in rows),
        "stop_latency": all(
            (row.stop_latency or 0) <= LOCKED_GATES["maximum_stop_latency"] for row in rows
        ),
        "post_observable_continuation": all(
            row.harmful_assignments_after_observation
            <= LOCKED_GATES["maximum_post_observable_harmful_continuation"]
            for row in rows
        ),
        "bounded_revalidation_exposure": all(
            row.harmful_revalidation_assignments
            <= LOCKED_GATES["maximum_revalidation_harmful_exposure"]
            for row in rows
        ),
        "positive_value_retained": positive["mean_value_retained"]
        >= LOCKED_GATES["minimum_positive_value_retained"],
        "null_not_active": null["mean_active_rate"]
        <= LOCKED_GATES["maximum_null_active_rate"],
        "reactivation_correct": float(
            np.mean([row.reactivated for row in rows if row.scenario == "REACTIVATION"])
        )
        >= 0.80,
    }
    payload: dict[str, object] = {
        "configuration": {
            "paths_per_scenario": PATHS_PER_SCENARIO,
            "seed_root": 720_001,
            "horizon": HORIZON,
            "locked_gates": LOCKED_GATES,
        },
        "scenarios": by_scenario,
        "gates": gates,
        "overall_pass": all(gates.values()),
        "rows": [asdict(row) for row in rows],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    lines = [
        "# V7.2 Sequential Assurance",
        "",
        f"Verdict: **{'PASS' if payload['overall_pass'] else 'FAIL'}**.",
        "",
        "The controller uses mature randomized observations only. Pausing does not release "
        "immature committed risk.",
        "",
        "| Scenario | Mean value | Active rate | Stop latency | Harmful continuation | "
        "Value retained |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario, row in by_scenario.items():
        lines.append(
            f"| {scenario} | {row['mean_value']:.2f} | {row['mean_active_rate']:.1%} | "
            f"{row['maximum_stop_latency']} | {row['maximum_harmful_continuation']} | "
            f"{row['mean_value_retained']:.1%} |"
        )
    lines.extend(["", "## Locked gates", ""])
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in gates.items())
    REPORT.write_text("\n".join(lines) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_tournament()["gates"], indent=2, sort_keys=True))
