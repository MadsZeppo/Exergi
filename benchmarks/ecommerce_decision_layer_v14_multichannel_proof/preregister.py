from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "configs"
MANIFESTS = ROOT / "manifests"
CALIBRATION_COMMIT = "9485e548491c0765f6a114014a35ae02fa19d589"

MERCHANT_FAMILIES = ("FASHION", "BEAUTY_SUPPLEMENTS", "HOME_GOODS", "MARKETPLACE")
ACTIONS = (
    "BAU_NO_ACTION",
    "EMAIL_REMINDER",
    "EMAIL_10_PERCENT_DISCOUNT",
    "SMS_REMINDER",
    "SMS_10_PERCENT_DISCOUNT",
    "FREE_SHIPPING",
    "PAID_RETARGETING",
    "ONSITE_PERSONALIZATION",
    "EMAIL_PLUS_RETARGETING",
    "SUPPRESS_DO_NOT_CONTACT",
)
WORLD_FAMILIES = (
    "NO_ACTIONABLE_OPPORTUNITY",
    "HOMOGENEOUS_POSITIVE_ACTION",
    "GLOBALLY_HARMFUL_ACTION",
    "PROFITABLE_STATIC_ACTION",
    "MATERIAL_CUSTOMER_HETEROGENEITY",
    "SPARSE_RESPONDERS",
    "CHANNEL_SUBSTITUTION",
    "CHANNEL_FATIGUE",
    "DISCOUNT_CANNIBALIZATION",
    "PULL_FORWARD",
    "DELAYED_REFUNDS",
    "INCOMPLETE_COSTS",
    "COMMON_SHOCK",
    "SEASONALITY_SHIFT",
    "PROPENSITY_SUPPORT_FAILURE",
    "DATA_CORRUPTION",
    "ABRUPT_REVERSAL",
    "GRADUAL_DRIFT",
    "NEW_UNSEEN_PRODUCTS",
    "LIMITED_SAMPLE_POWER",
    "RETURN_DRIVEN_REVERSAL",
    "DELIVERABILITY_FAILURE",
    "INVENTORY_CONSTRAINT",
    "BUDGET_CONSTRAINT",
    "NEW_MERCHANT_COLD_START",
)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merchant_manifest() -> dict[str, Any]:
    merchants: list[dict[str, Any]] = []
    for index in range(16):
        split = "DEVELOPMENT" if index < 8 else "VALIDATION" if index < 12 else "SEALED_TEST"
        family = MERCHANT_FAMILIES[(index // 2) % 4] if index < 8 else MERCHANT_FAMILIES[index % 4]
        region = {
            "DEVELOPMENT": "CENTERED_CALIBRATION_REGION",
            "VALIDATION": "DISJOINT_EDGE_CALIBRATION_REGION",
            "SEALED_TEST": "DISJOINT_STRESS_CALIBRATION_REGION",
        }[split]
        merchants.append(
            {
                "merchant_id": f"V14_M{index + 1:02d}",
                "family": family,
                "split": split,
                "eligible_customers": 20_000,
                "weeks": 52,
                "parameter_region": region,
                "customer_seed": 140_000 + index * 100 + 1,
                "event_seed": 140_000 + index * 100 + 2,
                "assignment_seed": 140_000 + index * 100 + 3,
                "truth_seed": 140_000 + index * 100 + 4,
                "shock_seed": 140_000 + index * 100 + 5,
            }
        )
    return {
        "development": [item for item in merchants if item["split"] == "DEVELOPMENT"],
        "validation": [item for item in merchants if item["split"] == "VALIDATION"],
        "sealed_test": [item for item in merchants if item["split"] == "SEALED_TEST"],
        "customer_overlap_allowed": False,
        "merchant_overlap_allowed": False,
        "validation_outcomes_generated": False,
        "validation_outcomes_opened": False,
        "sealed_outcomes_generated": False,
        "sealed_outcomes_opened": False,
        "schema_version": 1,
    }


def configs() -> dict[str, dict[str, Any]]:
    action_space = {
        "actions": list(ACTIONS),
        "channels": {
            "BAU_NO_ACTION": "NONE",
            "EMAIL_REMINDER": "EMAIL",
            "EMAIL_10_PERCENT_DISCOUNT": "EMAIL",
            "SMS_REMINDER": "SMS",
            "SMS_10_PERCENT_DISCOUNT": "SMS",
            "FREE_SHIPPING": "OWNED_CROSS_CHANNEL",
            "PAID_RETARGETING": "PAID_MEDIA",
            "ONSITE_PERSONALIZATION": "ONSITE",
            "EMAIL_PLUS_RETARGETING": "EMAIL_AND_PAID_MEDIA",
            "SUPPRESS_DO_NOT_CONTACT": "SUPPRESSION",
        },
        "dispositions": ["DO", "TEST", "AVOID", "NOT_ENOUGH_EVIDENCE"],
        "not_enough_evidence_execution": "BAU_NO_ACTION",
        "eligibility_fail_closed": [
            "MISSING_CONSENT",
            "CHANNEL_UNAVAILABLE",
            "FREQUENCY_CAP",
            "SUPPRESSION_LIST",
            "INSUFFICIENT_INVENTORY",
            "MISSING_CRITICAL_COST",
            "UNKNOWN_PROPENSITY",
            "INSUFFICIENT_SUPPORT",
            "BUDGET_EXHAUSTED",
            "UNRESOLVED_PRIOR_EXPOSURE",
            "PROHIBITED_ACTION",
        ],
        "schema_version": 1,
    }
    economics = {
        "currency": "SYNTHETIC_USD",
        "primary_outcome": "INCREMENTAL_CONTRIBUTION_PROFIT_PER_ELIGIBLE_CUSTOMER",
        "net_revenue_equation": "gross_revenue - discounts - refunds",
        "contribution_profit_equation": (
            "net_revenue + shipping_revenue - cogs - payment_fees - shipping_cost "
            "- shipping_subsidy - fulfilment_cost - return_shipping_cost "
            "- restocking_loss - channel_cost - switching_cost - other_variable_cost"
        ),
        "direct_action_cost": {
            "BAU_NO_ACTION": 0.0,
            "EMAIL_REMINDER": 0.02,
            "EMAIL_10_PERCENT_DISCOUNT": 0.03,
            "SMS_REMINDER": 0.06,
            "SMS_10_PERCENT_DISCOUNT": 0.07,
            "FREE_SHIPPING": 0.02,
            "PAID_RETARGETING": 0.45,
            "ONSITE_PERSONALIZATION": 0.04,
            "EMAIL_PLUS_RETARGETING": 0.48,
            "SUPPRESS_DO_NOT_CONTACT": 0.0,
        },
        "discount_funding": "10_PERCENT_OF_GROSS_REVENUE_ON_DISCOUNTED_PURCHASES",
        "critical_cost_fields": [
            "cogs",
            "payment_fees",
            "fulfilment_cost",
            "shipping_cost",
            "shipping_subsidy",
            "channel_cost",
        ],
        "missing_critical_cost": "DATA_NOT_READY",
        "materiality_formula": (
            "max(0.01 * mature_bau_cp_per_eligible_customer, direct_action_cost, "
            "switching_cost, family_minimum_commercial_amount)"
        ),
        "family_minimum_commercial_amount": {
            "FASHION": 0.40,
            "BEAUTY_SUPPLEMENTS": 0.25,
            "HOME_GOODS": 0.55,
            "MARKETPLACE": 0.35,
        },
        "schema_version": 1,
    }
    maturity = {
        "early_behavior_weeks": 1,
        "primary_purchase_weeks": 2,
        "economic_outcome_weeks": 4,
        "delayed_refund_stress_weeks": 8,
        "risk_release": "ONLY_AFTER_MATURE_ECONOMIC_OUTCOME",
        "unmatured_outcome": "PENDING_NOT_ZERO",
        "schema_version": 1,
    }
    support = {
        "known_logged_propensity_required": True,
        "minimum_action_propensity": 0.02,
        "minimum_policy_action_ess": 400,
        "minimum_local_action_ess": 100,
        "maximum_standardized_mean_difference": 0.10,
        "minimum_supported_folds": 4,
        "folds": 5,
        "unsupported_execution": "NOT_ENOUGH_EVIDENCE_TO_BAU",
        "no_propensity_clipping_without_report": True,
        "schema_version": 1,
    }
    candidates = {
        "comparators": [
            "BAU",
            "TREAT_ALL_PER_ACTION",
            "BEST_STATIC",
            "RULE_SEGMENT_POLICY",
            "COST_AWARE_HEURISTIC",
        ],
        "model_families": [
            "REGULARIZED_LINEAR_T_LEARNER",
            "TREE_T_LEARNER",
            "FOREST_T_LEARNER",
            "X_LEARNER",
            "R_LEARNER",
            "DR_LEARNER",
            "CAUSAL_FOREST_EQUIVALENT",
            "CONSERVATIVE_ENSEMBLE",
        ],
        "bau_forecasts": [
            "REGULARIZED_TWO_PART_MODEL",
            "GRADIENT_BOOSTED_TWO_PART_MODEL",
        ],
        "selection_metric": "HELD_OUT_INCREMENTAL_CONTRIBUTION_PROFIT_VS_PREVIOUS_HIERARCHY_LEVEL",
        "complexity_tie_break": "SIMPLER_POLICY_WINS",
        "maximum_promoted_policy_stacks": 1,
        "oracle_allowed_for_selection": False,
        "schema_version": 1,
    }
    gates = {
        "development_promotion": {
            "positive_point_vs_bau": True,
            "lower_95_vs_bau_gt": 0.0,
            "beats_best_static_required_for_personalization": True,
            "lower_95_vs_best_static_gt": 0.0,
            "net_value_exceeds_materiality": True,
            "positive_folds_required": 4,
            "folds": 5,
            "seed_direction_agreement_gte": 0.80,
            "world_family_direction_agreement_gte": 0.80,
            "placebos_pass": True,
            "unsupported_act": 0,
            "null_world_do_rate_lte": 0.05,
            "harmful_world_do_rate_lte": 0.01,
            "budget_violations": 0,
            "future_or_oracle_access": 0,
        },
        "validation_pass": {
            "pooled_cp_point_gt": 0.0,
            "pooled_cp_lower_95_gt": 0.0,
            "positive_all_merchant_families": True,
            "beats_static_world_share_gte": 0.75,
            "beats_heuristic_world_share_gte": 0.75,
            "observable_oracle_capture_gte": 0.60,
            "no_material_negative_family": True,
            "all_development_safety_gates_repeated": True,
        },
        "oracle_metrics_evaluation_only": True,
        "no_threshold_source": [
            "HILLSTROM",
            "V8",
            "V9",
            "JTPA",
            "PREVIOUS_FAILURE_RESULTS",
        ],
        "schema_version": 1,
    }
    risk = {
        "initial_test_exposure_fraction": 0.02,
        "maximum_unmatured_exposure_fraction": 0.05,
        "merchant_budget_formula": "0.0025 * mature_preperiod_annualized_bau_cp",
        "channel_action_budget_formula": "0.0008 * mature_preperiod_annualized_bau_cp",
        "reservation": (
            "max(model_credible_downside, empirical_downside, stress_downside, "
            "action_family_floor, merchant_floor)"
        ),
        "credible_harm_rule": "posterior_probability_incremental_cp_below_zero_gte_0.95",
        "stop_latency_batches": 1,
        "release_before_maturity_allowed": False,
        "reactivation": "NEW_POSITIVE_MATURE_EVIDENCE_AND_SUPPORT_REQUIRED",
        "maximum_revalidations": 1,
        "schema_version": 1,
    }
    dgp = {
        "authority": "REALITY_CALIBRATED_SEMI_SYNTHETIC_MECHANISM_BENCHMARK",
        "calibration_use": "AGGREGATE_OBSERVABLE_MARGINALS_ONLY",
        "customer_ids": "NEW_SYNTHETIC_IDS_NO_CROSS_SOURCE_JOIN",
        "merchant_families": list(MERCHANT_FAMILIES),
        "world_families": list(WORLD_FAMILIES),
        "customer_state": [
            "lifecycle",
            "recency",
            "frequency",
            "historical_value",
            "category_affinity",
            "product_affinity",
            "price_sensitivity",
            "channel_eligibility",
            "purchase_cadence",
            "return_propensity",
            "channel_fatigue",
        ],
        "evaluator_only": [
            "latent_response_type",
            "potential_outcomes",
            "true_cate",
            "true_best_action",
            "future_shocks",
            "future_returns",
            "response_parameters",
            "oracle_value",
        ],
        "economics": [
            "gross_revenue",
            "cogs",
            "discount_funding",
            "refunds",
            "shipping_subsidy",
            "payment_fees",
            "channel_send_cost",
            "paid_media_cost",
            "cannibalization",
            "pull_forward",
            "switching_cost",
            "incremental_contribution_profit",
        ],
        "response_parameter_regions": {
            "DEVELOPMENT": {"effect_scale": [0.80, 1.20], "shock_scale": [0.85, 1.15]},
            "VALIDATION": {"effect_scale": [0.55, 0.78], "shock_scale": [1.18, 1.40]},
            "SEALED_TEST": {"effect_scale": [1.22, 1.50], "shock_scale": [1.42, 1.70]},
        },
        "paired_common_random_numbers": True,
        "schema_version": 1,
    }
    reports = {
        "development": [
            "V14_MODEL_TOURNAMENT.md",
            "V14_DEVELOPMENT_REPORT.md",
            "V14_SEQUENTIAL_ASSURANCE.md",
            "V14_LEARNING_REPORT.md",
            "V14_FAILURE_DECOMPOSITION.md",
            "V14_DEVELOPMENT_RESULT.json",
        ],
        "freeze_only_if_development_passes": [
            "V14_FREEZE_MANIFEST.json",
            "V14_PRE_REVEAL_QA.json",
        ],
        "validation_only_after_freeze": ["V14_VALIDATION_REPORT.md", "V14_RESULT.json"],
        "sealed_only_after_validation_pass": ["V14_SEALED_REPORT.md"],
        "schema_version": 1,
    }
    return {
        "V14_ACTION_SPACE.json": action_space,
        "V14_CANDIDATE_MODELS.json": candidates,
        "V14_DGP_SPEC.json": dgp,
        "V14_ECONOMIC_RULES.json": economics,
        "V14_MATURITY_RULES.json": maturity,
        "V14_PASS_GATES.json": gates,
        "V14_REPORT_CONTRACT.json": reports,
        "V14_RISK_RULES.json": risk,
        "V14_SUPPORT_RULES.json": support,
    }


def preregister() -> dict[str, Any]:
    CONFIG.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    source_snapshot = ROOT / "manifests/V14_SOURCE_SNAPSHOT.json"
    calibration = ROOT / "V14_REALITY_CALIBRATION.json"
    if sha256(calibration) != "8484c16091a04ba27f9326f5d3e626a9eba907fe517a77d7a05e492b782f3e12":
        raise RuntimeError("V14 calibration artifact differs from immutable checkpoint")
    split = merchant_manifest()
    payloads = configs()
    for name, payload in payloads.items():
        (CONFIG / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    split_path = MANIFESTS / "V14_SPLIT_MANIFEST.json"
    split_path.write_text(json.dumps(split, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    seed_roots = {
        "merchant_seeds": {
            item["merchant_id"]: {
                key: value for key, value in item.items() if key.endswith("_seed")
            }
            for group in (split["development"], split["validation"], split["sealed_test"])
            for item in group
        },
        "model_seed": 141_001,
        "fold_seed": 141_002,
        "bootstrap_seed": 141_003,
        "placebo_seed": 141_004,
        "replay_seed": 141_005,
        "schema_version": 1,
    }
    seeds_path = MANIFESTS / "V14_SEED_ROOTS.json"
    seeds_path.write_text(
        json.dumps(seed_roots, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "phase": "PREREGISTERED_BEFORE_ANY_SYNTHETIC_OUTCOME_GENERATION",
        "calibration_commit": CALIBRATION_COMMIT,
        "calibration_artifact_sha256": sha256(calibration),
        "source_snapshot_sha256": sha256(source_snapshot),
        "preregister_code_sha256": sha256(Path(__file__)),
        "config_hashes": {
            name: sha256(CONFIG / name) for name in sorted(payloads)
        },
        "split_manifest_sha256": sha256(split_path),
        "seed_roots_sha256": sha256(seeds_path),
        "development_outcomes_generated": False,
        "validation_outcomes_generated": False,
        "validation_outcomes_opened": False,
        "sealed_outcomes_generated": False,
        "sealed_outcomes_opened": False,
        "thresholds_imported_from_previous_benchmarks": False,
        "schema_version": 1,
    }
    (ROOT / "V14_PREREGISTRATION_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    preregister()
