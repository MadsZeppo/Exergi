from __future__ import annotations

import csv
import json
import subprocess

from benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.qualification import (
    QUALIFICATION_AUDIT,
    QUALIFICATION_RESULT,
    SOURCE_MANIFEST,
    TIMING_DICTIONARY,
    WORKSPACE,
    verify_immutable_history,
    verify_participant_contract,
    verify_qualification_checkpoint,
    verify_raw_source,
    verify_timing_contract,
)


def test_v13_official_archive_checksum_size_crc_and_read_only() -> None:
    verify_raw_source()


def test_v13_raw_storage_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "data/raw/jtpa/jtpa_national_evaluation.zip"],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_v13_source_manifest_has_only_official_upjohn_authority() -> None:
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["publisher"] == "W.E. Upjohn Institute for Employment Research"
    assert manifest["official_download_url"].startswith("https://www.upjohn.org/")
    assert manifest["archive"]["crc_check"] == "PASS"


def test_v13_participant_identity_and_assignment_contract() -> None:
    audit = verify_participant_contract()
    assert audit["full_rows"] == audit["full_unique_recid"] == 20_601
    assert audit["mature_rows"] == 15_134
    assert (audit["mature_treated"], audit["mature_control"]) == (10_145, 4_989)


def test_v13_randomization_srm_and_balance_pass() -> None:
    audit = json.loads(QUALIFICATION_AUDIT.read_text(encoding="utf-8"))
    assert audit["assignment"]["primary_propensity"] == 2 / 3
    assert audit["srm"]["status"] == "PASS"
    assert audit["srm"]["p_value"] > 0.05
    assert audit["balance"]["max_abs_smd"] < 0.1


def test_v13_timing_dictionary_covers_every_analytic_field() -> None:
    verify_timing_contract()
    with TIMING_DICTIONARY.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 470


def test_v13_actual_participation_and_outcomes_are_rejected_as_features() -> None:
    with TIMING_DICTIONARY.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ppd = [row for row in rows if row["source"] == "ppd_dat.dta"]
    earnings = [
        row
        for row in rows
        if row["variable"].startswith(("newern", "totern", "uiern"))
    ]
    assert not any(row["policy_status"] == "POLICY_ALLOWED" for row in ppd)
    assert all(row["timing_class"] == "OUTCOME_ONLY" for row in earnings)


def test_v13_protected_characteristics_are_audit_only() -> None:
    with TIMING_DICTIONARY.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    protected = {"age", "race", "sex", "male", "female"}
    selected = [
        row for row in rows if row["source"] == "expbif.dta" and row["variable"] in protected
    ]
    assert selected
    assert all(row["policy_status"] == "AUDIT_ONLY_PROTECTED" for row in selected)


def test_v13_qualification_is_outcome_isolated_earnings_only() -> None:
    result = verify_qualification_checkpoint()
    assert result["qualified"] is True
    assert result["qualification_status"] == "QUALIFIED_FOR_RANDOMIZED_EARNINGS_ONLY"
    assert result["access_control"]["raw_outcome_values_analyzed"] is False
    assert result["access_control"]["validation_outcomes_opened"] is False


def test_v13_cost_contract_cannot_claim_net_economic_value() -> None:
    result = json.loads(QUALIFICATION_RESULT.read_text(encoding="utf-8"))
    assert result["claim_authority_at_qualification"] == (
        "REAL_RANDOMIZED_EARNINGS_POLICY_VALUE_ONLY"
    )
    assert result["cost_authority"].startswith("NO_REPRODUCIBLE_PERSON_LEVEL")


def test_v13_preserves_immutable_v8_v9_v10_v12_history() -> None:
    verify_immutable_history()
