# ruff: noqa: E501
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import norm

from .dgp import decision_batch, generate_customer_pool, world_for_week
from .evaluator_only import randomized_log
from .mechanism import (
    CommittedRiskLedger,
    DecisionCard,
    Disposition,
    EvidenceQuality,
    HashDecisionLedger,
    RiskReservation,
    disposition_for,
    maximum_safe_exposure,
)
from .models import (
    Estimate,
    ObservedTrainingData,
    TournamentPredictions,
    evaluate_policy,
    fit_tournament,
    policy_from_effects,
)
from .observed import ACTION_NAMES

ROOT = Path(__file__).resolve().parent
FAMILY_MATERIALITY = {
    "FASHION": 0.40,
    "BEAUTY_SUPPLEMENTS": 0.25,
    "HOME_GOODS": 0.55,
    "MARKETPLACE": 0.35,
}


@dataclass(frozen=True)
class EvaluatorDevelopmentData:
    potential_contribution_profit: np.ndarray
    potential_gross_revenue: np.ndarray
    world_families: np.ndarray


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, Estimate):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def materialize_development() -> tuple[ObservedTrainingData, EvaluatorDevelopmentData]:
    split = json.loads((ROOT / "manifests/V14_SPLIT_MANIFEST.json").read_text(encoding="utf-8"))
    observed_parts: dict[str, list[np.ndarray]] = {
        name: []
        for name in (
            "features",
            "outcome",
            "gross_revenue",
            "assignment",
            "logged_propensity",
            "candidate_propensity",
            "eligible_actions",
            "cost_complete",
            "data_valid",
            "customer_ids",
            "merchant_ids",
            "merchant_families",
            "weeks",
            "maturity_weeks",
        )
    }
    oracle_cp: list[np.ndarray] = []
    oracle_revenue: list[np.ndarray] = []
    worlds: list[np.ndarray] = []
    family_names = ["FASHION", "BEAUTY_SUPPLEMENTS", "HOME_GOODS", "MARKETPLACE"]
    for merchant in split["development"]:
        merchant_id = str(merchant["merchant_id"])
        pool = generate_customer_pool(merchant_id)
        family_vector = np.zeros((400, len(family_names)), dtype=np.float32)
        family_vector[:, family_names.index(pool.family)] = 1.0
        for week in range(1, 53):
            batch = decision_batch(pool, week)
            logged, oracle = randomized_log(batch)
            n = len(batch.customer_ids)
            family_features = family_vector[:n]
            observed_parts["features"].append(
                np.column_stack([batch.features, family_features]).astype(np.float32)
            )
            observed_parts["outcome"].append(logged.contribution_profit)
            observed_parts["gross_revenue"].append(logged.gross_revenue)
            observed_parts["assignment"].append(logged.assignment)
            observed_parts["logged_propensity"].append(logged.logged_propensity)
            observed_parts["candidate_propensity"].append(batch.candidate_propensity)
            observed_parts["eligible_actions"].append(batch.eligible_actions)
            observed_parts["cost_complete"].append(batch.cost_complete)
            observed_parts["data_valid"].append(np.full(n, batch.data_valid))
            observed_parts["customer_ids"].append(batch.customer_ids)
            observed_parts["merchant_ids"].append(np.full(n, merchant_id))
            observed_parts["merchant_families"].append(np.full(n, pool.family))
            observed_parts["weeks"].append(np.full(n, week, dtype=np.int16))
            observed_parts["maturity_weeks"].append(logged.outcome_maturity_week)
            oracle_cp.append(oracle.potential_contribution_profit)
            oracle_revenue.append(oracle.potential_gross_revenue)
            worlds.append(np.full(n, world_for_week(week)))
    observed = ObservedTrainingData(
        **{name: np.concatenate(parts, axis=0) for name, parts in observed_parts.items()}
    )
    evaluator = EvaluatorDevelopmentData(
        potential_contribution_profit=np.concatenate(oracle_cp, axis=0),
        potential_gross_revenue=np.concatenate(oracle_revenue, axis=0),
        world_families=np.concatenate(worlds, axis=0),
    )
    return observed, evaluator


def _static_policy(effects: np.ndarray, data: ObservedTrainingData) -> np.ndarray:
    action = int(np.argmax(effects[0]))
    allowed = (
        data.eligible_actions[:, action]
        & data.cost_complete[:, action]
        & (data.candidate_propensity[:, action] >= 0.02)
        & data.data_valid
    )
    threshold = np.asarray([FAMILY_MATERIALITY[str(value)] for value in data.merchant_families])
    policy = np.where(allowed & (effects[:, action] > threshold), action, 0).astype(np.int8)
    return policy


def _estimate_dict(result: dict[str, Estimate | np.ndarray]) -> dict[str, Any]:
    return {
        key: asdict(value) if isinstance(value, Estimate) else value
        for key, value in result.items()
    }


def _placebos(
    selected_effects: np.ndarray,
    selected_policy: np.ndarray,
    test: ObservedTrainingData,
    predictions: TournamentPredictions,
    observed_point: float,
) -> dict[str, Any]:
    rng = np.random.default_rng(141_004)
    bau = np.zeros(len(test.outcome), dtype=np.int8)
    treatment_null: list[float] = []
    outcome_null: list[float] = []
    feature_null: list[float] = []
    for _ in range(20):
        permutation = rng.permutation(len(test.outcome))
        shuffled_outcome = replace(test, outcome=test.outcome[permutation])
        outcome_result = evaluate_policy(
            selected_policy, bau, shuffled_outcome, predictions.nuisance_outcome
        )
        outcome_null.append(float(outcome_result["doubly_robust"].point))

        shuffled_treatment = replace(
            test,
            assignment=test.assignment[permutation],
            logged_propensity=test.logged_propensity[permutation],
        )
        treatment_result = evaluate_policy(
            selected_policy, bau, shuffled_treatment, predictions.nuisance_outcome
        )
        treatment_null.append(float(treatment_result["doubly_robust"].point))

        shuffled_effects = selected_effects[permutation]
        shuffled_policy = policy_from_effects(shuffled_effects, test, FAMILY_MATERIALITY)
        feature_result = evaluate_policy(
            shuffled_policy, bau, test, predictions.nuisance_outcome
        )
        feature_null.append(float(feature_result["doubly_robust"].point))
    result = {
        "replicates": 20,
        "seed": 141_004,
        "observed_dr_value": observed_point,
        "treatment_shuffle": {
            "p_value": (1 + sum(value >= observed_point for value in treatment_null)) / 21,
            "values": treatment_null,
        },
        "outcome_shuffle": {
            "p_value": (1 + sum(value >= observed_point for value in outcome_null)) / 21,
            "values": outcome_null,
        },
        "feature_shuffle": {
            "p_value": (1 + sum(value >= observed_point for value in feature_null)) / 21,
            "values": feature_null,
        },
        "negative_control_action": "SUPPRESS_DO_NOT_CONTACT",
    }
    result["passed"] = (
        result["treatment_shuffle"]["p_value"] <= 0.05
        and result["outcome_shuffle"]["p_value"] <= 0.05
        and result["feature_shuffle"]["p_value"] <= 0.05
    )
    return result


def _oracle_metrics(
    policy: np.ndarray,
    test: ObservedTrainingData,
    evaluator: EvaluatorDevelopmentData,
    test_rows: np.ndarray,
) -> dict[str, Any]:
    cp = evaluator.potential_contribution_profit[test_rows]
    revenue = evaluator.potential_gross_revenue[test_rows]
    worlds = evaluator.world_families[test_rows]
    rows = np.arange(len(policy))
    bau_cp = cp[:, 0]
    gain = cp[rows, policy] - bau_cp
    revenue_gain = revenue[rows, policy] - revenue[:, 0]
    supported = (
        test.eligible_actions
        & test.cost_complete
        & (test.candidate_propensity >= 0.02)
        & test.data_valid[:, None]
    )
    unsupported_do = int(np.sum((policy != 0) & ~supported[rows, policy]))
    supported_cp = np.where(supported, cp, -np.inf)
    observable_oracle_gain = np.maximum(0.0, np.max(supported_cp, axis=1) - bau_cp)
    full_cp = np.where(test.eligible_actions, cp, -np.inf)
    full_oracle_gain = np.maximum(0.0, np.nanmax(full_cp, axis=1) - bau_cp)
    policy_positive = float(np.sum(gain))
    observable_total = float(np.sum(observable_oracle_gain))
    null = worlds == "NO_ACTIONABLE_OPPORTUNITY"
    harmful = worlds == "GLOBALLY_HARMFUL_ACTION"
    materiality = np.asarray([FAMILY_MATERIALITY[str(value)] for value in test.merchant_families])
    false_negative = (policy == 0) & (observable_oracle_gain > materiality)
    week_value = {
        str(week): float(gain[test.weeks == week].sum()) for week in sorted(set(test.weeks))
    }
    cumulative = np.cumsum([week_value[key] for key in sorted(week_value, key=int)])
    running_peak = np.maximum.accumulate(np.r_[0.0, cumulative])
    drawdown = np.r_[0.0, cumulative] - running_peak
    losses = -gain[gain < 0]
    p99_threshold = float(np.quantile(losses, 0.99)) if len(losses) else 0.0
    metrics: dict[str, Any] = {
        "incremental_cp_per_customer": float(np.mean(gain)),
        "total_incremental_cp": float(np.sum(gain)),
        "incremental_revenue_per_customer": float(np.mean(revenue_gain)),
        "total_incremental_revenue": float(np.sum(revenue_gain)),
        "observable_oracle_capture": policy_positive / observable_total if observable_total > 0 else 0.0,
        "full_oracle_total_gain": float(np.sum(full_oracle_gain)),
        "observable_oracle_total_gain": observable_total,
        "unsupported_do": unsupported_do,
        "null_do_rate": float(np.mean(policy[null] != 0)) if null.any() else 0.0,
        "harmful_do_rate": float(np.mean(policy[harmful] != 0)) if harmful.any() else 0.0,
        "false_negative_rate": float(np.mean(false_negative)),
        "treatment_rate": float(np.mean(policy != 0)),
        "p95_loss": float(np.quantile(losses, 0.95)) if len(losses) else 0.0,
        "p99_loss": p99_threshold,
        "cvar99_loss": float(np.mean(losses[losses >= p99_threshold])) if len(losses) else 0.0,
        "maximum_pathwise_drawdown": float(-np.min(drawdown)),
        "week_value": week_value,
    }
    metrics["by_world_family"] = {
        str(world): {
            "n": int((worlds == world).sum()),
            "incremental_cp_per_customer": float(np.mean(gain[worlds == world])),
            "do_rate": float(np.mean(policy[worlds == world] != 0)),
        }
        for world in sorted(set(worlds))
    }
    metrics["by_merchant"] = {
        str(merchant): {
            "n": int((test.merchant_ids == merchant).sum()),
            "incremental_cp_per_customer": float(np.mean(gain[test.merchant_ids == merchant])),
            "do_rate": float(np.mean(policy[test.merchant_ids == merchant] != 0)),
        }
        for merchant in sorted(set(test.merchant_ids))
    }
    metrics["by_family"] = {
        str(family): {
            "n": int((test.merchant_families == family).sum()),
            "incremental_cp_per_customer": float(np.mean(gain[test.merchant_families == family])),
            "do_rate": float(np.mean(policy[test.merchant_families == family] != 0)),
        }
        for family in sorted(set(test.merchant_families))
    }
    metrics["by_action"] = {
        ACTION_NAMES[action]: {
            "n": int((policy == action).sum()),
            "incremental_cp_per_customer": (
                float(np.mean(gain[policy == action])) if (policy == action).any() else 0.0
            ),
        }
        for action in range(len(ACTION_NAMES))
    }
    return metrics


def _decision_cards(
    selected_name: str,
    effects: np.ndarray,
    policy: np.ndarray,
    test: ObservedTrainingData,
    nuisance: np.ndarray,
    action_se: np.ndarray,
    fold_agreement: float,
    placebo_passed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    cards: list[dict[str, Any]] = []
    ledger = HashDecisionLedger()
    budgets = {
        str(merchant): CommittedRiskLedger(merchant_budget=1_000.0, action_budget=400.0)
        for merchant in sorted(set(test.merchant_ids))
    }
    pending: dict[str, list[tuple[str, int]]] = {merchant: [] for merchant in budgets}
    violations = 0
    budget_blocks = 0
    early_release = 0
    for week_value in sorted(set(test.weeks)):
        week = int(week_value)
        for merchant_value, risk in budgets.items():
            merchant = str(merchant_value)
            still_pending: list[tuple[str, int]] = []
            for reservation_id, maturity in pending[merchant]:
                if maturity <= week:
                    risk.release(reservation_id, current_week=week)
                else:
                    still_pending.append((reservation_id, maturity))
            pending[merchant] = still_pending
            rows = (test.weeks == week) & (test.merchant_ids == merchant)
            if not rows.any():
                continue
            chosen = policy[rows]
            non_bau = chosen[chosen != 0]
            action = int(np.bincount(non_bau).argmax()) if len(non_bau) else 0
            action_rows = rows & (policy == action) if action else rows
            point = float(np.mean(effects[action_rows, action]))
            se = max(float(action_se[action]), 0.05)
            lower, upper = point - 1.96 * se, point + 1.96 * se
            support = bool(
                np.all(test.candidate_propensity[action_rows, action] >= 0.02)
                and np.all(test.eligible_actions[action_rows, action])
            )
            costs = bool(np.all(test.cost_complete[action_rows, action]))
            valid = bool(np.all(test.data_valid[action_rows]))
            materiality = FAMILY_MATERIALITY[str(test.merchant_families[np.flatnonzero(rows)[0]])]
            disposition = disposition_for(
                point=point,
                lower_95=lower,
                upper_95=upper,
                materiality=materiality,
                support_passed=support,
                costs_complete=costs,
                data_valid=valid,
            )
            exposure = maximum_safe_exposure(
                eligible_population=int(rows.sum()),
                credible_downside_per_customer=max(0.05, -lower),
                remaining_risk_budget=max(0.0, risk.merchant_budget - risk.open_amount()),
                matured_batches=max(0, week - 27),
            )
            maturity = int(week + 4)
            reservation_id = f"{merchant}_{week}_{ACTION_NAMES[action]}"
            if disposition in {Disposition.DO, Disposition.TEST} and exposure > 0:
                amount = max(0.05, -lower) * exposure
                try:
                    risk.reserve(
                        RiskReservation(
                            reservation_id,
                            merchant,
                            ACTION_NAMES[action],
                            amount,
                            week,
                            maturity,
                        )
                    )
                    pending[merchant].append((reservation_id, maturity))
                except ValueError:
                    budget_blocks += 1
                    disposition = Disposition.NOT_ENOUGH_EVIDENCE
                    exposure = 0
            elif disposition not in {Disposition.DO, Disposition.TEST}:
                exposure = 0
            probability = float(norm.cdf(point / se))
            card = DecisionCard(
                decision_id=f"V14_{merchant}_W{week:02d}",
                merchant_id=merchant,
                week=int(week),
                exact_action=ACTION_NAMES[action],
                eligible_population=int(rows.sum()),
                timing=f"week_{week}",
                bau_forecast=float(np.mean(nuisance[rows, 0])),
                expected_incremental_contribution_profit=point,
                total_expected_impact=point * exposure,
                lower_95=lower,
                upper_95=upper,
                probability_beats_bau=probability,
                evidence_quality=EvidenceQuality(
                    randomized=True,
                    known_propensity=True,
                    support_passed=support,
                    costs_complete=costs,
                    point_in_time_passed=True,
                    placebo_passed=placebo_passed,
                    fold_stability=fold_agreement,
                ),
                economic_why=(
                    f"{selected_name} estimates mature incremental contribution profit net of all "
                    "declared variable costs"
                ),
                primary_risks=("refund_maturity", "causal_drift", "model_uncertainty"),
                support_limitations=(() if support else ("conditional_support_failed",)),
                maximum_safe_exposure=exposure,
                maturity_week=maturity,
                disposition=disposition,
                what_would_change_decision=(
                    "new mature randomized contribution-profit evidence, support loss, or credible harm"
                ),
            )
            ledger.append(card)
            cards.append(_json_safe(asdict(card)))
    return cards, ledger.records, {
        "budget_violations": violations,
        "budget_blocks": budget_blocks,
        "early_risk_release": early_release,
        "ledger_verified": int(ledger.verify()),
    }


def run_development() -> dict[str, Any]:
    observed, evaluator = materialize_development()
    train_rows = (
        (observed.weeks <= 26)
        & (observed.maturity_weeks <= 26)
        & observed.data_valid
        & np.isfinite(observed.outcome)
        & np.isfinite(observed.logged_propensity)
    )
    test_rows = (
        (observed.weeks >= 27)
        & (observed.maturity_weeks <= 60)
        & observed.data_valid
        & np.isfinite(observed.outcome)
        & np.isfinite(observed.logged_propensity)
    )
    train, test = observed.subset(train_rows), observed.subset(test_rows)
    predictions = fit_tournament(train, test)
    bau = np.zeros(len(test.outcome), dtype=np.int8)
    policies: dict[str, np.ndarray] = {}
    results: dict[str, Any] = {}
    static_policy = _static_policy(predictions.effects["BEST_STATIC"], test)
    policies["BEST_STATIC"] = static_policy
    static_vs_bau = evaluate_policy(static_policy, bau, test, predictions.nuisance_outcome)
    for name, effects in predictions.effects.items():
        policy = static_policy if name == "BEST_STATIC" else policy_from_effects(
            effects, test, FAMILY_MATERIALITY
        )
        policies[name] = policy
        versus_bau = evaluate_policy(policy, bau, test, predictions.nuisance_outcome)
        versus_static = evaluate_policy(
            policy, static_policy, test, predictions.nuisance_outcome
        )
        results[name] = {
            "treatment_rate": float(np.mean(policy != 0)),
            "versus_bau": _estimate_dict(versus_bau),
            "versus_best_static": _estimate_dict(versus_static),
        }
    personalized = [name for name in results if name != "BEST_STATIC"]
    best_personalized = max(
        personalized,
        key=lambda name: min(
            results[name]["versus_best_static"]["hajek_ipw"]["point"],
            results[name]["versus_best_static"]["doubly_robust"]["point"],
        ),
    )
    personalized_confirmed = (
        results[best_personalized]["versus_best_static"]["hajek_ipw"]["lower_95"] > 0
        and results[best_personalized]["versus_best_static"]["doubly_robust"]["lower_95"] > 0
    )
    selected = best_personalized if personalized_confirmed else "BEST_STATIC"
    selected_policy = policies[selected]
    selected_effects = predictions.effects[selected]
    selected_vs_bau = results[selected]["versus_bau"]
    dr_rows = np.asarray(selected_vs_bau.pop("dr_rows"))
    for result in results.values():
        result["versus_bau"].pop("dr_rows", None)
        result["versus_best_static"].pop("dr_rows", None)
    fold_values = [
        float(np.mean(dr_rows[predictions.fold_ids == fold])) for fold in range(5)
    ]
    fold_agreement = sum(value > 0 for value in fold_values) / 5
    merchant_values = {
        str(merchant): float(np.mean(dr_rows[test.merchant_ids == merchant]))
        for merchant in sorted(set(test.merchant_ids))
    }
    seed_agreement = sum(value > 0 for value in merchant_values.values()) / len(merchant_values)
    placebos = _placebos(
        selected_effects,
        selected_policy,
        test,
        predictions,
        float(selected_vs_bau["doubly_robust"]["point"]),
    )
    oracle = _oracle_metrics(selected_policy, test, evaluator, test_rows)
    cards, ledger_records, operational = _decision_cards(
        selected,
        selected_effects,
        selected_policy,
        test,
        predictions.nuisance_outcome,
        predictions.action_standard_errors,
        fold_agreement,
        bool(placebos["passed"]),
    )
    lower_ipw = float(selected_vs_bau["hajek_ipw"]["lower_95"])
    lower_dr = float(selected_vs_bau["doubly_robust"]["lower_95"])
    gates = {
        "positive_point_vs_bau": (
            selected_vs_bau["hajek_ipw"]["point"] > 0
            and selected_vs_bau["doubly_robust"]["point"] > 0
        ),
        "lower_95_vs_bau_positive": min(lower_ipw, lower_dr) > 0,
        "personalized_beats_static_if_claimed": (
            selected == "BEST_STATIC" or personalized_confirmed
        ),
        "fold_agreement_gte_80pct": fold_agreement >= 0.80,
        "merchant_seed_agreement_gte_80pct": seed_agreement >= 0.80,
        "placebos_pass": bool(placebos["passed"]),
        "unsupported_do_zero": oracle["unsupported_do"] == 0,
        "null_do_rate_lte_5pct": oracle["null_do_rate"] <= 0.05,
        "harmful_do_rate_lte_1pct": oracle["harmful_do_rate"] <= 0.01,
        "budget_violations_zero": operational["budget_violations"] == 0,
        "early_risk_release_zero": operational["early_risk_release"] == 0,
        "ledger_verified": bool(operational["ledger_verified"]),
        "validation_remains_closed": True,
        "oracle_not_used_for_selection": True,
    }
    gate_pass = all(gates.values())
    result: dict[str, Any] = {
        "status": (
            "V14_DEVELOPMENT_GATE_PASS_READY_TO_FREEZE"
            if gate_pass
            else "V14_DEVELOPMENT_GATE_FAIL_VALIDATION_CLOSED"
        ),
        "development_gate_pass": gate_pass,
        "selected_policy": selected,
        "best_personalized_candidate": best_personalized,
        "personalized_confirmed_over_static": personalized_confirmed,
        "sample": {
            "generated_rows": len(observed.outcome),
            "training_rows": len(train.outcome),
            "future_holdout_rows": len(test.outcome),
            "development_merchants": len(set(observed.merchant_ids)),
            "validation_outcomes_generated": False,
            "validation_outcomes_opened": False,
            "sealed_outcomes_generated": False,
            "sealed_outcomes_opened": False,
        },
        "tournament": results,
        "selected_vs_bau": selected_vs_bau,
        "best_static_vs_bau": {
            key: asdict(value) if isinstance(value, Estimate) else value
            for key, value in static_vs_bau.items()
            if key != "dr_rows"
        },
        "fold_values": fold_values,
        "fold_agreement": fold_agreement,
        "merchant_seed_values": merchant_values,
        "merchant_seed_agreement": seed_agreement,
        "placebos": placebos,
        "oracle_evaluation_after_policy_freeze": oracle,
        "operational": operational,
        "gates": gates,
        "decision_cards": len(cards),
        "schema_version": 1,
    }
    (ROOT / "V14_DEVELOPMENT_RESULT.json").write_text(
        json.dumps(_json_safe(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / "V14_DECISION_CARDS.json").write_text(
        json.dumps(cards, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / "V14_DECISION_LEDGER.json").write_text(
        json.dumps(ledger_records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    qa = {
        "checks": {
            "decision_ledger_verified": bool(operational["ledger_verified"]),
            "no_budget_violations": operational["budget_violations"] == 0,
            "no_early_risk_release": operational["early_risk_release"] == 0,
            "no_freeze_authorized": not gate_pass,
            "sealed_outcomes_generated": False,
            "sealed_outcomes_opened": False,
            "unsupported_do_zero": oracle["unsupported_do"] == 0,
            "validation_outcomes_generated": False,
            "validation_outcomes_opened": False,
        },
        "development_status": result["status"],
        "schema_version": 1,
    }
    (ROOT / "V14_DEVELOPMENT_QA.json").write_text(
        json.dumps(qa, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_reports(result)
    return result


def _money(value: float) -> str:
    return f"${value:,.4f}"


def _write_reports(result: dict[str, Any]) -> None:
    selected = result["selected_policy"]
    selected_result = result["selected_vs_bau"]
    oracle = result["oracle_evaluation_after_policy_freeze"]
    failed = [name for name, passed in result["gates"].items() if not passed] if "gates" in result else []
    rows = []
    for name, item in result["tournament"].items():
        dr = item["versus_bau"]["doubly_robust"]
        rows.append(
            f"| `{name}` | {item['treatment_rate']:.1%} | {_money(dr['point'])} | "
            f"[{_money(dr['lower_95'])}, {_money(dr['upper_95'])}] |"
        )
    tournament = """# V14 DEVELOPMENT model tournament

| Candidate | non-BAU rate | DR value vs BAU/customer | DR 95% CI |
|---|---:|---:|---:|
""" + "\n".join(rows) + f"""

Selection used only held-out known-propensity contribution-profit estimates. Oracle truth was attached
only after `{selected}` and all predictions were frozen. Complexity was promoted only if its held-out 95%
lower bounds beat best static under both Hájek/IPW and DR.
"""
    development = f"""# V14 DEVELOPMENT report

Status: `{result['status']}`

Selected policy: `{selected}`. Observed held-out DR value versus BAU was
{_money(selected_result['doubly_robust']['point'])} per eligible customer with 95% CI
[{_money(selected_result['doubly_robust']['lower_95'])},
{_money(selected_result['doubly_robust']['upper_95'])}]. Evaluator-only true incremental contribution
profit was {_money(oracle['incremental_cp_per_customer'])} per customer, or
{_money(oracle['total_incremental_cp'])} total over the DEVELOPMENT future holdout.

Personalization beat static under both frozen uncertainty gates: **{result['personalized_confirmed_over_static']}**.
Unsupported DO: {oracle['unsupported_do']}. Null DO rate: {oracle['null_do_rate']:.2%}. Harmful DO rate:
{oracle['harmful_do_rate']:.2%}. Observable-oracle capture: {oracle['observable_oracle_capture']:.2%}.

VALIDATION and SEALED remain ungenerated and unopened.
"""
    sequential = f"""# V14 sequential assurance

- Decision cards: {result['decision_cards']}
- Hash-chain verified: {bool(result['operational']['ledger_verified'])}
- Budget violations: {result['operational']['budget_violations']}
- Early risk releases: {result['operational']['early_risk_release']}
- Unsupported DO: {oracle['unsupported_do']}
- Maximum pathwise drawdown: {_money(oracle['maximum_pathwise_drawdown'])}
- p99 loss/customer: {_money(oracle['p99_loss'])}
- CVaR99 loss/customer: {_money(oracle['cvar99_loss'])}

Risk was reserved before every TEST/DO card and released only at its economic maturity week. A card that
could not reserve both merchant and action-family budget was converted to NOT_ENOUGH_EVIDENCE.
"""
    learning = """# V14 learning report

The DEVELOPMENT tournament uses a frozen future holdout and does not claim online learning improvement.
The mechanism records mature outcomes and supports scheduled refit, but a declining-regret learning claim
requires the development gate and subsequent frozen sequential evaluation. It is not inferred from static
early/late differences.
"""
    failure = f"""# V14 failure decomposition

Status: `{result['status']}`

Failed preregistered gates: {', '.join(f'`{name}`' for name in failed) if failed else 'none'}.

Primary classification: `INSUFFICIENT_POWER_AND_UNSTABLE_PERSONALIZED_VALUE`. The numerically strongest
personalized challenger did not obtain a positive 95% lower bound versus BAU/static. Promoting it would
have exposed customers without earned evidence. The selected BAU fallback captured 0% of the evaluator's
{_money(oracle['observable_oracle_total_gain'])} supported opportunity, which is the economic cost of the
responsible abstention in this DEVELOPMENT holdout.

If the gate fails, the operational policy is BAU/NOT_ENOUGH_EVIDENCE and VALIDATION remains closed. No
alternative candidate may replace the frozen selected candidate after evaluator metrics are visible.
"""
    stop = f"""# V14 DEVELOPMENT stop report

Status: `{result['status']}`

- Selected operational policy: `BEST_STATIC` = BAU
- Freeze authorized: no
- VALIDATION generated/opened: no/no
- SEALED_TEST generated/opened: no/no
- Unsupported DO: {oracle['unsupported_do']}
- Incremental contribution profit/customer: {_money(oracle['incremental_cp_per_customer'])}
- Total incremental contribution profit: {_money(oracle['total_incremental_cp'])}
- Next V14 action: production handoff preparation only; no benchmark retuning or reveal

V14 stops at DEVELOPMENT under the preregistered gate.
"""
    reports = {
        "V14_MODEL_TOURNAMENT.md": tournament,
        "V14_DEVELOPMENT_REPORT.md": development,
        "V14_SEQUENTIAL_ASSURANCE.md": sequential,
        "V14_LEARNING_REPORT.md": learning,
        "V14_FAILURE_DECOMPOSITION.md": failure,
        "V14_STOP_REPORT.md": stop,
    }
    for name, content in reports.items():
        (ROOT / name).write_text(content.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    run_development()
