"""Read-only CLI for merchant extract readiness, shadow assignment and mature ITT analysis."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from decision_engine.decision.experiment import two_arm_sample_size

from .analysis import analyze_itt
from .contracts import (
    AssignmentRecord,
    CampaignEligibilityRecord,
    ChannelCostRecord,
    CustomerRecord,
    DeliveryRecord,
    DiscountRecord,
    ExperimentArmContract,
    OrderLineRecord,
    OrderRecord,
    OutcomeRecord,
    ProductRecord,
    ReturnRecord,
    WinbackExperimentContract,
)
from .experiment import (
    assign_cohort,
    eligible_cohort,
    export_assignments_idempotent,
    freeze_contract,
    stable_hash,
)
from .ledger import AppendOnlyPilotLedger
from .validation import load_records, validate_tables


def _read_optional(directory: Path, name: str, model: type[Any]) -> tuple[Any, ...]:
    for suffix in (".parquet", ".csv"):
        path = directory / f"{name}{suffix}"
        if path.exists():
            return load_records(path, model)
    return ()


def readiness(input_dir: Path) -> dict[str, object]:
    customers = _read_optional(input_dir, "customers", CustomerRecord)
    orders = _read_optional(input_dir, "orders", OrderRecord)
    order_lines = _read_optional(input_dir, "order_lines", OrderLineRecord)
    products = _read_optional(input_dir, "products", ProductRecord)
    discounts = _read_optional(input_dir, "discounts", DiscountRecord)
    returns = _read_optional(input_dir, "returns", ReturnRecord)
    eligibility = _read_optional(input_dir, "eligibility", CampaignEligibilityRecord)
    delivery = _read_optional(input_dir, "delivery", DeliveryRecord)
    channel_costs = _read_optional(input_dir, "channel_costs", ChannelCostRecord)
    report = validate_tables(
        customers=customers,
        orders=orders,
        order_lines=order_lines,
        products=products,
        discounts=discounts,
        returns=returns,
        eligibility=eligibility,
        delivery=delivery,
        channel_costs=channel_costs,
    )
    required_nonempty = {
        "customers": customers,
        "orders": orders,
        "order_lines": order_lines,
        "products": products,
        "eligibility": eligibility,
        "channel_costs": channel_costs,
    }
    missing = [name for name, rows in required_nonempty.items() if not rows]
    issues = [issue.__dict__ for issue in report.issues]
    issues.extend(
        {"code": "MISSING_REQUIRED_TABLE", "table": name, "detail": "no rows"}
        for name in missing
    )
    return {
        "status": "READY_FOR_SHADOW" if not issues else "DATA_NOT_READY",
        "read_only": True,
        "autonomous_action_permitted": False,
        "row_counts": report.row_counts,
        "issues": issues,
    }


def prepare_shadow(input_dir: Path, config_path: Path, output_dir: Path) -> dict[str, object]:
    ready = readiness(input_dir)
    if ready["status"] != "READY_FOR_SHADOW":
        return ready
    config = json.loads(config_path.read_text())
    eligibility = list(_read_optional(input_dir, "eligibility", CampaignEligibilityRecord))
    snapshot_at = datetime.fromisoformat(config["eligibility_snapshot_at"])
    cohort = eligible_cohort(
        eligibility,
        snapshot_at=snapshot_at,
        inactivity_days=int(config["inactivity_days"]),
        minimum_purchases=int(config["minimum_historical_purchases"]),
        parallel_campaign_exclusion_days=int(config["parallel_campaign_exclusion_days"]),
    )
    per_arm = two_arm_sample_size(
        outcome_standard_deviation=float(config["outcome_standard_deviation"]),
        minimum_detectable_effect=float(config["minimum_detectable_effect"]),
        alpha=float(config.get("alpha", 0.05)),
        power=float(config.get("power", 0.80)),
    )
    planned = 2 * per_arm
    if len(cohort) < planned:
        return {
            **ready,
            "status": "DATA_NOT_READY",
            "issues": [
                *cast(list[object], ready["issues"]),
                {
                    "code": "UNDERPOWERED_COHORT",
                    "table": "eligibility",
                    "detail": f"requires {planned}, found {len(cohort)}",
                },
            ],
        }
    arms = (
        ExperimentArmContract(
            name="BAU_CONTROL", allocation_probability=0.5, is_control=True
        ),
        ExperimentArmContract(
            name=str(config.get("intervention_name", "WINBACK_MESSAGE")),
            allocation_probability=0.5,
            action_parameters=dict(config.get("action_parameters", {})),
        ),
    )
    created_at = datetime.fromisoformat(config["created_at"])
    contract = WinbackExperimentContract(
        experiment_id=str(config["experiment_id"]),
        merchant_id=str(config["merchant_id"]),
        created_at=created_at,
        eligibility_snapshot_at=snapshot_at,
        inactivity_days=int(config["inactivity_days"]),
        minimum_historical_purchases=int(config["minimum_historical_purchases"]),
        parallel_campaign_exclusion_days=int(config["parallel_campaign_exclusion_days"]),
        eligibility_hash=stable_hash(cohort),
        outcome_maturity_days=int(config["outcome_maturity_days"]),
        strata_fields=tuple(config.get("strata_fields", ())),
        arms=arms,
        minimum_detectable_effect=float(config["minimum_detectable_effect"]),
        planned_sample_size=planned,
        alpha=float(config.get("alpha", 0.05)),
        power=float(config.get("power", 0.80)),
        expected_effect_per_customer=config.get("expected_effect_per_customer"),
        randomization_seed=str(config["randomization_seed"]),
    )
    frozen_at = datetime.fromisoformat(config["frozen_at"])
    frozen = freeze_contract(contract, eligible_customer_ids=cohort, frozen_at=frozen_at)
    assigned_at = datetime.fromisoformat(config["assigned_at"])
    rows = assign_cohort(frozen, eligible_customer_ids=cohort, assigned_at=assigned_at)
    output_dir.mkdir(parents=True, exist_ok=True)
    contract_path = output_dir / "frozen_experiment_contract.json"
    encoded_contract = json.dumps(frozen.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if contract_path.exists() and contract_path.read_text() != encoded_contract:
        raise RuntimeError("frozen contract already exists with different content")
    contract_path.write_text(encoded_contract)
    assignment_hash = export_assignments_idempotent(rows, output_dir / "assignment_export.csv")
    ledger = AppendOnlyPilotLedger(output_dir / "decision_ledger.jsonl")
    if not ledger.records():
        ledger.append(
            record_id=f"{frozen.experiment_id}:prediction",
            record_type="PRE_OUTCOME_EXPECTATION",
            payload={
                "contract_hash": frozen.contract_hash,
                "expected_effect_per_customer": frozen.expected_effect_per_customer,
                "authority": frozen.expected_effect_authority,
            },
            recorded_at=frozen_at,
        )
        ledger.append(
            record_id=f"{frozen.experiment_id}:assignment",
            record_type="IMMUTABLE_ASSIGNMENT_EXPORT",
            payload={"rows": len(rows), "assignment_export_sha256": assignment_hash},
            recorded_at=assigned_at,
        )
    return {
        "status": "SHADOW_ASSIGNMENT_READY_NOT_SENT",
        "read_only": True,
        "autonomous_action_permitted": False,
        "eligible_customers": len(cohort),
        "planned_sample_size": planned,
        "contract_hash": frozen.contract_hash,
        "assignment_export_sha256": assignment_hash,
        "ledger_valid": ledger.verify(),
    }


def _load_assignments(path: Path) -> tuple[AssignmentRecord, ...]:
    with path.open(newline="", encoding="utf-8") as source:
        return tuple(AssignmentRecord.model_validate(row) for row in csv.DictReader(source))


def analyze_shadow(
    output_dir: Path, outcomes_path: Path, analyzed_at: datetime
) -> dict[str, object]:
    contract = WinbackExperimentContract.model_validate_json(
        (output_dir / "frozen_experiment_contract.json").read_text()
    )
    assignments = _load_assignments(output_dir / "assignment_export.csv")
    outcomes = load_records(outcomes_path, OutcomeRecord)
    result = analyze_itt(contract, assignments, outcomes, analyzed_at=analyzed_at)
    report_path = output_dir / "mature_itt_result.json"
    encoded = json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n"
    if report_path.exists() and report_path.read_text() != encoded:
        raise RuntimeError("mature result is immutable; a different analysis already exists")
    report_path.write_text(encoded)
    ledger = AppendOnlyPilotLedger(output_dir / "decision_ledger.jsonl")
    record_id = f"{contract.experiment_id}:mature-result"
    if not any(row["record_id"] == record_id for row in ledger.records()):
        ledger.append(
            record_id=record_id,
            record_type="MATURE_RANDOMIZED_ITT_RESULT",
            payload=result.to_dict(),
            recorded_at=analyzed_at,
        )
    return result.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    ready_parser = subparsers.add_parser("readiness")
    ready_parser.add_argument("input_dir", type=Path)
    prepare_parser = subparsers.add_parser("prepare-shadow")
    prepare_parser.add_argument("input_dir", type=Path)
    prepare_parser.add_argument("config", type=Path)
    prepare_parser.add_argument("output_dir", type=Path)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("output_dir", type=Path)
    analyze_parser.add_argument("outcomes", type=Path)
    analyze_parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    if args.command == "readiness":
        payload = readiness(args.input_dir)
    elif args.command == "prepare-shadow":
        payload = prepare_shadow(args.input_dir, args.config, args.output_dir)
    else:
        payload = analyze_shadow(args.output_dir, args.outcomes, datetime.fromisoformat(args.as_of))
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
