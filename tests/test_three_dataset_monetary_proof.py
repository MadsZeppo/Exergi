from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.three_dataset_monetary_proof.audit import audit_immutable_proofs
from decision_engine.monetary_decision_contract import (
    CostAuthority,
    MonetaryAuthority,
    MonetaryDecisionContract,
    MonetaryProofRow,
    RandomizedAction,
)

ROOT = Path("benchmarks/three_dataset_monetary_proof")


def _contract(
    authority: MonetaryAuthority = MonetaryAuthority.GROSS_REVENUE,
) -> MonetaryDecisionContract:
    return MonetaryDecisionContract(
        study_id="fixture",
        randomized_unit="customer",
        actions=(
            RandomizedAction("BAU", True, 0.5),
            RandomizedAction("ACTION", False, 0.5),
        ),
        assignment_field="assignment",
        propensity_authority="known randomization",
        pretreatment_features=("history",),
        monetary_outcome="revenue",
        currency="USD",
        action_cost="none observed",
        cost_authority=CostAuthority.NONE_OBSERVED,
        maturity_rule="30 days",
        eligible_population="randomized customers",
        claim_authority=authority,
    )


def test_contract_requires_one_bau_and_valid_propensities() -> None:
    assert _contract().bau_action == "BAU"
    with pytest.raises(ValueError, match="exactly one"):
        MonetaryDecisionContract(
            **{
                **_contract().__dict__,
                "actions": (
                    RandomizedAction("A", False, 0.5),
                    RandomizedAction("B", False, 0.5),
                ),
            }
        )


def test_profit_authority_requires_complete_economic_components() -> None:
    with pytest.raises(ValueError, match="every economic component"):
        _contract(MonetaryAuthority.CONTRIBUTION_PROFIT)


def test_pass_row_requires_positive_lower_bound() -> None:
    with pytest.raises(ValueError, match="positive lower"):
        MonetaryProofRow("x", "ACT", 0, 1, 1, 10, -1, 2, "USD", "revenue", True)


def test_immutable_v8_v9_artifact_audit_passes_without_raw_data() -> None:
    result = audit_immutable_proofs()
    assert all(result["v8"]["checks"].values())
    assert all(result["v9_study3"]["checks"].values())
    assert result["v8"]["pass"] is True
    assert result["v9_study3"]["pass"] is True


def test_third_dataset_stops_before_outcomes_and_reveal() -> None:
    qualification = json.loads((ROOT / "THIRD_DATASET_QUALIFICATION.json").read_text())
    assert qualification["status"] == "THIRD_MONETARY_DATASET_NOT_FOUND"
    assert qualification["outcome_columns_inspected"] is False
    assert qualification["validation_or_sealed_created"] is False
    assert qualification["selected_alternative"]["row_level_data_present"] is False
