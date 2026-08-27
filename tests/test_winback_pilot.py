from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from decision_engine.pilots.winback.analysis import analyze_itt
from decision_engine.pilots.winback.contracts import (
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
from decision_engine.pilots.winback.experiment import (
    assign_cohort,
    eligible_cohort,
    export_assignments_idempotent,
    freeze_contract,
    stable_hash,
)
from decision_engine.pilots.winback.ledger import AppendOnlyPilotLedger
from decision_engine.pilots.winback.runner import prepare_shadow
from decision_engine.pilots.winback.validation import validate_tables
from decision_engine.safety.legacy_oracle_quarantine import scan_policy_source

NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


def _contract(cohort: tuple[str, ...]) -> WinbackExperimentContract:
    contract = WinbackExperimentContract(
        experiment_id="pilot-1",
        merchant_id="merchant-1",
        created_at=NOW,
        eligibility_snapshot_at=NOW,
        inactivity_days=90,
        minimum_historical_purchases=2,
        parallel_campaign_exclusion_days=30,
        eligibility_hash=stable_hash(cohort),
        outcome_maturity_days=30,
        arms=(
            ExperimentArmContract(
                name="BAU_CONTROL", allocation_probability=0.5, is_control=True
            ),
            ExperimentArmContract(name="WINBACK_MESSAGE", allocation_probability=0.5),
        ),
        minimum_detectable_effect=0.5,
        planned_sample_size=40,
        randomization_seed="frozen-secret-seed",
    )
    return freeze_contract(contract, eligible_customer_ids=cohort, frozen_at=NOW)


def _assignments(n: int = 100) -> tuple[AssignmentRecord, ...]:
    cohort = tuple(f"customer-{index:03d}" for index in range(n))
    return assign_cohort(
        _contract(cohort), eligible_customer_ids=cohort, assigned_at=NOW + timedelta(minutes=1)
    )


def _outcomes(
    assignments: tuple[AssignmentRecord, ...],
    *,
    effect: float = 1.0,
) -> tuple[OutcomeRecord, ...]:
    rows = []
    for index, assignment in enumerate(assignments):
        treatment_effect = effect if assignment.arm == "WINBACK_MESSAGE" else 0.0
        rows.append(
            OutcomeRecord(
                experiment_id=assignment.experiment_id,
                merchant_id=assignment.merchant_id,
                customer_id=assignment.customer_id,
                measured_at=NOW + timedelta(days=31),
                currency="DKK",
                net_revenue=10 + treatment_effect + (index % 3) * 0.1,
                merchant_funded_discount=1,
                refunds_returns=1,
                cogs=5,
                shipping_subsidy=1,
                payment_transaction_cost=1,
                channel_cost=1,
            )
        )
    return tuple(rows)


def test_eligibility_uses_only_snapshot_history_and_exclusions() -> None:
    rows = [
        CampaignEligibilityRecord(
            customer_id="eligible",
            snapshot_at=NOW,
            historical_purchase_count=2,
            last_purchase_at=NOW - timedelta(days=100),
            last_parallel_campaign_at=None,
            consent=True,
            suppressed=False,
        ),
        CampaignEligibilityRecord(
            customer_id="recent",
            snapshot_at=NOW,
            historical_purchase_count=4,
            last_purchase_at=NOW - timedelta(days=5),
            last_parallel_campaign_at=None,
            consent=True,
            suppressed=False,
        ),
    ]
    assert eligible_cohort(
        rows,
        snapshot_at=NOW,
        inactivity_days=90,
        minimum_purchases=2,
        parallel_campaign_exclusion_days=30,
    ) == ("eligible",)


def test_randomization_is_deterministic_stratified_and_propensity_correct() -> None:
    first = _assignments()
    second = _assignments()
    assert first == second
    assert sum(row.arm == "BAU_CONTROL" for row in first) == 50
    assert {row.propensity for row in first} == {0.5}
    assert len({row.assignment_hash for row in first}) == len(first)


def test_assignment_export_is_idempotent_and_immutable(tmp_path: Path) -> None:
    rows = _assignments()
    path = tmp_path / "assignment.csv"
    assert export_assignments_idempotent(rows, path) == export_assignments_idempotent(rows, path)
    changed = (rows[0].model_copy(update={"arm": "TAMPERED"}), *rows[1:])
    with pytest.raises(RuntimeError, match="immutable assignment export"):
        export_assignments_idempotent(changed, path)


def test_outcome_cannot_be_analyzed_before_maturity() -> None:
    assignments = _assignments()
    result = analyze_itt(
        _contract(tuple(row.customer_id for row in assignments)),
        assignments,
        _outcomes(assignments),
        analyzed_at=NOW + timedelta(days=29),
    )
    assert result.status == "DATA_NOT_READY"
    assert "OUTCOME_NOT_MATURE" in result.reason_codes
    assert not result.profit_claim_permitted


def test_mature_itt_is_primary_and_scales_only_on_positive_lower_bound() -> None:
    assignments = _assignments()
    result = analyze_itt(
        _contract(tuple(row.customer_id for row in assignments)),
        assignments,
        _outcomes(assignments, effect=1.0),
        analyzed_at=NOW + timedelta(days=31),
    )
    assert result.status == "ANALYZED"
    assert result.primary_estimand == "CUSTOMER_LEVEL_INTENTION_TO_TREAT"
    assert result.decision == "SCALE"
    assert result.results[0].effect_per_eligible_customer == pytest.approx(1.0, abs=0.05)


def test_missing_cost_fails_closed_without_profit_language() -> None:
    assignments = _assignments()
    outcomes = list(_outcomes(assignments))
    outcomes[0] = outcomes[0].model_copy(update={"cogs": None})
    result = analyze_itt(
        _contract(tuple(row.customer_id for row in assignments)),
        assignments,
        tuple(outcomes),
        analyzed_at=NOW + timedelta(days=31),
    )
    assert result.status == "DATA_NOT_READY"
    assert result.results == ()
    assert not result.profit_claim_permitted
    assert "MISSING_REQUIRED_COST" in result.reason_codes


def test_srm_differential_attrition_and_contamination_are_detected() -> None:
    assignments = _assignments()
    contract = _contract(tuple(row.customer_id for row in assignments))
    badly_allocated = tuple(
        row.model_copy(update={"arm": "WINBACK_MESSAGE"}) if index < 40 else row
        for index, row in enumerate(assignments)
    )
    outcomes = tuple(
        row
        for row in _outcomes(badly_allocated)
        if not (
            next(item for item in badly_allocated if item.customer_id == row.customer_id).arm
            == "WINBACK_MESSAGE"
            and int(row.customer_id[-3:]) % 5 == 0
        )
    )
    delivery = (
        DeliveryRecord(
            experiment_id="pilot-1",
            customer_id=assignments[0].customer_id,
            arm="WRONG_ARM",
            delivered_at=NOW + timedelta(minutes=2),
            exposed_at=None,
        ),
    )
    result = analyze_itt(
        contract,
        badly_allocated,
        outcomes,
        analyzed_at=NOW + timedelta(days=31),
        deliveries=delivery,
    )
    assert "SAMPLE_RATIO_MISMATCH" in result.reason_codes
    assert "DIFFERENTIAL_ATTRITION" in result.reason_codes
    assert "TREATMENT_CONTAMINATION" in result.reason_codes


def test_return_known_inside_window_reduces_mature_itt() -> None:
    assignments = _assignments()
    baseline = list(_outcomes(assignments))
    treatment_index = next(
        index for index, row in enumerate(assignments) if row.arm == "WINBACK_MESSAGE"
    )
    baseline[treatment_index] = baseline[treatment_index].model_copy(
        update={"refunds_returns": 6.0}
    )
    result = analyze_itt(
        _contract(tuple(row.customer_id for row in assignments)),
        assignments,
        tuple(baseline),
        analyzed_at=NOW + timedelta(days=31),
    )
    assert result.results[0].effect_per_eligible_customer < 1.0


def test_append_only_ledger_detects_tampering_and_duplicate_ids(tmp_path: Path) -> None:
    ledger = AppendOnlyPilotLedger(tmp_path / "ledger.jsonl")
    ledger.append(record_id="prediction", record_type="PRE_OUTCOME", payload={"effect": 1})
    ledger.append(record_id="outcome", record_type="MATURE_OUTCOME", payload={"effect": 0.5})
    assert ledger.verify()
    with pytest.raises(ValueError, match="immutable and unique"):
        ledger.append(record_id="prediction", record_type="OTHER", payload={})
    path = tmp_path / "ledger.jsonl"
    path.write_text(path.read_text().replace('"effect":1', '"effect":2'))
    assert not ledger.verify()


def test_table_validation_detects_duplicates_currency_leakage_and_costs() -> None:
    customer = CustomerRecord(
        customer_id="c1",
        created_at=NOW - timedelta(days=400),
        timezone="Europe/Copenhagen",
        currency="DKK",
        consent=True,
        suppressed=False,
    )
    order = OrderRecord(
        order_id="o1",
        customer_id="c1",
        ordered_at=NOW - timedelta(days=100),
        currency="DKK",
        gross_item_sales=100,
        line_discounts=0,
        shipping_revenue=0,
        payment_transaction_cost=None,
    )
    line = OrderLineRecord(
        order_line_id="l1",
        order_id="o1",
        product_id="p1",
        quantity=1,
        gross_sales=100,
        discount=0,
        cogs=None,
    )
    product = ProductRecord(product_id="p1", category="core", currency="EUR", unit_cogs=40)
    eligibility = CampaignEligibilityRecord(
        customer_id="c1",
        snapshot_at=NOW,
        historical_purchase_count=2,
        last_purchase_at=NOW + timedelta(days=1),
        last_parallel_campaign_at=None,
        consent=True,
        suppressed=False,
    )
    discount = DiscountRecord(
        discount_id="d1", order_id="o1", amount=1, merchant_funded_amount=None, currency="DKK"
    )
    returned = ReturnRecord(
        return_id="r1",
        order_id="o1",
        returned_at=NOW - timedelta(days=101),
        refund_amount=5,
        currency="DKK",
    )
    channel = ChannelCostRecord(
        experiment_id="pilot-1",
        customer_id="c1",
        channel_cost=None,
        shipping_subsidy=None,
        currency="DKK",
    )
    report = validate_tables(
        customers=(customer, customer),
        orders=(order,),
        order_lines=(line,),
        products=(product,),
        discounts=(discount,),
        returns=(returned,),
        eligibility=(eligibility,),
        channel_costs=(channel,),
    )
    codes = {issue.code for issue in report.issues}
    assert {"DUPLICATE_ID", "CURRENCY_MISMATCH", "FUTURE_LEAKAGE"} <= codes
    assert {"MISSING_COGS", "MISSING_PAYMENT_COST", "MISSING_ACTION_COST"} <= codes


def test_pilot_policy_source_cannot_import_legacy_oracle_paths() -> None:
    root = Path(__file__).resolve().parents[1] / "src/decision_engine/pilots/winback"
    assert scan_policy_source(tuple(root.glob("*.py"))) == ()


def test_synthetic_fixture_exercises_read_only_shadow_flow(tmp_path: Path) -> None:
    """Integration fixture validates plumbing only; it is not product evidence."""

    extract = tmp_path / "extract"
    output = tmp_path / "output"
    extract.mkdir()
    customer_ids = [f"fixture-{index:03d}" for index in range(40)]
    pl.DataFrame(
        [
            {
                "customer_id": customer_id,
                "created_at": (NOW - timedelta(days=500)).isoformat(),
                "timezone": "Europe/Copenhagen",
                "currency": "DKK",
                "consent": True,
                "suppressed": False,
            }
            for customer_id in customer_ids
        ]
    ).write_csv(extract / "customers.csv")
    pl.DataFrame(
        [
            {
                "order_id": f"order-{index}",
                "customer_id": customer_id,
                "ordered_at": (NOW - timedelta(days=120)).isoformat(),
                "currency": "DKK",
                "gross_item_sales": 100,
                "line_discounts": 0,
                "shipping_revenue": 0,
                "payment_transaction_cost": 2,
            }
            for index, customer_id in enumerate(customer_ids)
        ]
    ).write_csv(extract / "orders.csv")
    pl.DataFrame(
        [
            {
                "order_line_id": f"line-{index}",
                "order_id": f"order-{index}",
                "product_id": "product-1",
                "quantity": 1,
                "gross_sales": 100,
                "discount": 0,
                "cogs": 40,
            }
            for index in range(40)
        ]
    ).write_csv(extract / "order_lines.csv")
    pl.DataFrame(
        [{"product_id": "product-1", "category": "core", "currency": "DKK", "unit_cogs": 40}]
    ).write_csv(extract / "products.csv")
    pl.DataFrame(
        [
            {
                "customer_id": customer_id,
                "snapshot_at": NOW.isoformat(),
                "historical_purchase_count": 2,
                "last_purchase_at": (NOW - timedelta(days=120)).isoformat(),
                "last_parallel_campaign_at": None,
                "consent": True,
                "suppressed": False,
            }
            for customer_id in customer_ids
        ]
    ).write_csv(extract / "eligibility.csv")
    pl.DataFrame(
        [
            {
                "experiment_id": "fixture-only",
                "customer_id": customer_id,
                "channel_cost": 0.1,
                "shipping_subsidy": 0,
                "currency": "DKK",
            }
            for customer_id in customer_ids
        ]
    ).write_csv(extract / "channel_costs.csv")
    config = {
        "experiment_id": "fixture-only",
        "merchant_id": "fixture-merchant",
        "eligibility_snapshot_at": NOW.isoformat(),
        "created_at": NOW.isoformat(),
        "frozen_at": (NOW + timedelta(minutes=1)).isoformat(),
        "assigned_at": (NOW + timedelta(minutes=2)).isoformat(),
        "inactivity_days": 90,
        "minimum_historical_purchases": 2,
        "parallel_campaign_exclusion_days": 30,
        "outcome_maturity_days": 30,
        "minimum_detectable_effect": 1.0,
        "outcome_standard_deviation": 0.1,
        "randomization_seed": "fixture-seed-not-commercial",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(__import__("json").dumps(config))
    result = prepare_shadow(extract, config_path, output)
    assert result["status"] == "SHADOW_ASSIGNMENT_READY_NOT_SENT"
    assert result["autonomous_action_permitted"] is False
    assert result["ledger_valid"] is True
    assert (output / "assignment_export.csv").exists()
