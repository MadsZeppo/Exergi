from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.development import ROOT


def _load(name: str) -> object:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_v14_development_failed_closed_without_validation_or_freeze() -> None:
    result = _load("V14_DEVELOPMENT_RESULT.json")
    assert result["status"] == "V14_DEVELOPMENT_GATE_FAIL_VALIDATION_CLOSED"
    assert result["development_gate_pass"] is False
    assert result["selected_policy"] == "BEST_STATIC"
    assert result["sample"]["validation_outcomes_generated"] is False
    assert result["sample"]["validation_outcomes_opened"] is False
    assert result["sample"]["sealed_outcomes_generated"] is False
    assert not (ROOT / "V14_FREEZE_MANIFEST.json").exists()
    assert not (ROOT / "V14_VALIDATION_REPORT.md").exists()


def test_v14_development_compared_every_preregistered_candidate() -> None:
    result = _load("V14_DEVELOPMENT_RESULT.json")
    assert len(result["tournament"]) == 10
    assert result["best_personalized_candidate"] == "TREE_T_LEARNER"
    challenger = result["tournament"]["TREE_T_LEARNER"]
    assert challenger["versus_bau"]["doubly_robust"]["point"] > 0
    assert challenger["versus_bau"]["doubly_robust"]["lower_95"] < 0
    assert result["personalized_confirmed_over_static"] is False


def test_v14_bau_fallback_has_no_unsupported_or_harmful_do() -> None:
    result = _load("V14_DEVELOPMENT_RESULT.json")
    oracle = result["oracle_evaluation_after_policy_freeze"]
    assert oracle["unsupported_do"] == 0
    assert oracle["null_do_rate"] == 0.0
    assert oracle["harmful_do_rate"] == 0.0
    assert oracle["total_incremental_cp"] == 0.0
    assert result["operational"]["budget_violations"] == 0
    assert result["operational"]["early_risk_release"] == 0


def test_v14_decision_cards_separate_probability_from_evidence_quality() -> None:
    cards = _load("V14_DECISION_CARDS.json")
    assert len(cards) == 200
    required = {
        "exact_action",
        "eligible_population",
        "timing",
        "bau_forecast",
        "expected_incremental_contribution_profit",
        "total_expected_impact",
        "lower_95",
        "upper_95",
        "probability_beats_bau",
        "evidence_quality",
        "economic_why",
        "primary_risks",
        "support_limitations",
        "maximum_safe_exposure",
        "maturity_week",
        "disposition",
        "what_would_change_decision",
    }
    assert required <= set(cards[0])
    assert cards[0]["probability_beats_bau"] == 0.5
    assert cards[0]["evidence_quality"]["placebo_passed"] is False
    assert cards[0]["maximum_safe_exposure"] == 0


def test_v14_persisted_decision_ledger_hash_chain_verifies() -> None:
    records = _load("V14_DECISION_LEDGER.json")
    previous = "GENESIS"
    for record in records:
        encoded = json.dumps(
            {"payload": record["payload"], "previous_hash": previous},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        assert record["previous_hash"] == previous
        assert record["record_hash"] == hashlib.sha256(encoded).hexdigest()
        previous = record["record_hash"]


def test_v14_development_qa_records_closed_downstream_splits() -> None:
    qa = _load("V14_DEVELOPMENT_QA.json")
    assert qa["checks"]["no_freeze_authorized"] is True
    assert qa["checks"]["validation_outcomes_generated"] is False
    assert qa["checks"]["validation_outcomes_opened"] is False
    assert qa["checks"]["sealed_outcomes_generated"] is False
    assert qa["checks"]["sealed_outcomes_opened"] is False


def test_v14_frontend_is_outside_development_artifact_scope() -> None:
    assert all("frontend" not in path.name.lower() for path in Path(ROOT).iterdir())
