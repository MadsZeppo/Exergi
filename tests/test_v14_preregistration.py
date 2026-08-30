from __future__ import annotations

import hashlib
import json

from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.preregister import (
    ACTIONS,
    CONFIG,
    MERCHANT_FAMILIES,
    ROOT,
    WORLD_FAMILIES,
    configs,
    merchant_manifest,
)


def _load(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_v14_preregistered_splits_are_merchant_disjoint_and_outcome_closed() -> None:
    manifest = merchant_manifest()
    groups = [manifest["development"], manifest["validation"], manifest["sealed_test"]]
    ids = [{item["merchant_id"] for item in group} for group in groups]
    assert len(ids[0]) == 8 and len(ids[1]) == len(ids[2]) == 4
    assert not ids[0] & ids[1] and not ids[0] & ids[2] and not ids[1] & ids[2]
    assert all(item["eligible_customers"] == 20_000 for group in groups for item in group)
    assert all(item["weeks"] == 52 for group in groups for item in group)
    assert {item["family"] for group in groups for item in group} == set(MERCHANT_FAMILIES)
    assert manifest["validation_outcomes_generated"] is False
    assert manifest["sealed_outcomes_opened"] is False


def test_v14_action_world_and_candidate_contracts_are_complete() -> None:
    assert len(ACTIONS) == 10
    assert len(WORLD_FAMILIES) >= 20
    assert "SUPPRESS_DO_NOT_CONTACT" in ACTIONS
    assert "DELAYED_REFUNDS" in WORLD_FAMILIES
    payloads = configs()
    candidates = payloads["V14_CANDIDATE_MODELS.json"]
    assert "DR_LEARNER" in candidates["model_families"]
    assert candidates["oracle_allowed_for_selection"] is False


def test_v14_missing_cost_support_and_risk_rules_fail_closed() -> None:
    payloads = configs()
    assert payloads["V14_ECONOMIC_RULES.json"]["missing_critical_cost"] == "DATA_NOT_READY"
    support = payloads["V14_SUPPORT_RULES.json"]
    assert support["known_logged_propensity_required"] is True
    assert support["unsupported_execution"] == "NOT_ENOUGH_EVIDENCE_TO_BAU"
    risk = payloads["V14_RISK_RULES.json"]
    assert risk["release_before_maturity_allowed"] is False
    assert risk["stop_latency_batches"] == 1


def test_v14_no_threshold_is_imported_from_prior_benchmark_results() -> None:
    gates = configs()["V14_PASS_GATES.json"]
    assert set(gates["no_threshold_source"]) == {
        "HILLSTROM",
        "V8",
        "V9",
        "JTPA",
        "PREVIOUS_FAILURE_RESULTS",
    }


def test_v14_preregistration_manifest_hashes_configs_before_outcomes() -> None:
    manifest = _load("V14_PREREGISTRATION_MANIFEST.json")
    assert manifest["phase"] == "PREREGISTERED_BEFORE_ANY_SYNTHETIC_OUTCOME_GENERATION"
    assert manifest["development_outcomes_generated"] is False
    assert manifest["validation_outcomes_opened"] is False
    assert manifest["sealed_outcomes_opened"] is False
    for name, expected in manifest["config_hashes"].items():
        assert hashlib.sha256((CONFIG / name).read_bytes()).hexdigest() == expected
