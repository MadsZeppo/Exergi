from __future__ import annotations

import json
import subprocess

from benchmarks.ecommerce_decision_layer_v12_penn_bonus.integrity import (
    QUALIFICATION_RESULT,
    ROOT,
    SCHEMA_AUDIT,
    SOURCE_MANIFEST,
    WORKSPACE,
    header,
    verify_immutable_history,
    verify_outcome_isolation,
    verify_qualification_checkpoint,
    verify_raw_source,
    verify_schema_without_outcomes,
)


def test_v12_official_zip_checksum_size_crc_and_read_only() -> None:
    verify_raw_source()


def test_v12_raw_storage_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "data/raw/penn_bonus/source/PA_ReempBonus.zip"],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_v12_header_only_schema_counts_match_official_documentation() -> None:
    schema = verify_schema_without_outcomes()
    assert schema["records_observations"] == 17_513
    assert len(schema["records_columns"]) == 189
    assert schema["survey_observations"] == 5_678
    assert len(schema["survey_columns"]) == 641


def test_v12_records_have_assignment_but_no_claimant_id() -> None:
    audit = json.loads(SCHEMA_AUDIT.read_text(encoding="utf-8"))
    assert audit["records"]["assignment_column"] == "tg"
    assert audit["records"]["persistent_claimant_id_present"] is False
    assert audit["records"]["one_assignment_per_claimant_auditable"] is False


def test_v12_survey_id_does_not_create_primary_join_authority() -> None:
    audit = json.loads(SCHEMA_AUDIT.read_text(encoding="utf-8"))
    assert audit["survey"]["identifier_column"] == "id"
    assert audit["survey"]["records_join_key_present"] is False
    assert audit["survey"]["post_treatment_bonus_recipient_oversampling"] is True
    assert audit["survey"]["usable_for_primary_policy_evaluation"] is False


def test_v12_schema_reader_reads_only_first_header_line() -> None:
    source = header.__code__.co_names
    assert "readline" in source
    assert "readlines" not in source


def test_v12_source_manifest_records_wrong_external_report_identity() -> None:
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    mismatch = manifest["documents"]["external_final_report_link_mismatch"]
    assert mismatch["actual_identity"] == "WASHINGTON_REEMPLOYMENT_BONUS_EXPERIMENT"
    assert mismatch["excluded_from_v12_evidence"] is True
    assert manifest["documents"]["archive_final_report"]["identity"] == (
        "PENNSYLVANIA_REEMPLOYMENT_BONUS_DEMONSTRATION"
    )


def test_v12_outcome_isolation_and_no_downstream_artifacts() -> None:
    result = verify_outcome_isolation()
    assert not any(result["access_control"].values())


def test_v12_qualification_fails_closed_with_no_claim_authority() -> None:
    result = verify_qualification_checkpoint()
    assert result["qualified"] is False
    assert result["claim_authority"] == "NONE"
    assert result["final_status"] == "V12_DATA_NOT_CAUSALLY_QUALIFIED"


def test_v12_no_monetary_or_dkk_result_is_created() -> None:
    result = json.loads(QUALIFICATION_RESULT.read_text(encoding="utf-8"))
    assert result["access_control"]["raw_outcome_values_analyzed"] is False
    report = (ROOT / "V12_STOP_REPORT.md").read_text(encoding="utf-8")
    assert "no USD/DKK conversion" in report
    assert "This is a data-contract stop" in report


def test_v12_immutable_v8_v9_v10_history() -> None:
    verify_immutable_history()
