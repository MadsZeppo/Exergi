from __future__ import annotations

import json

from benchmarks.ecommerce_decision_layer_v10_mtlift.integrity import (
    QUALIFICATION_RESULT,
    ROOT,
    SOURCE_MANIFEST,
    WORKSPACE,
    verify_immutable_history,
    verify_outcome_isolation,
    verify_qualification_checkpoint,
    verify_reference_hashes,
)


def test_v10_official_reference_hashes_match() -> None:
    observed = verify_reference_hashes()
    assert set(observed) == {
        "references/2402.03379.pdf",
        "references/README-379b315.md",
    }


def test_v10_raw_storage_is_gitignored() -> None:
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", "data/raw/mt_lift/references/2402.03379.pdf"],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_v10_source_is_official_but_dataset_was_not_acquired() -> None:
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["official_repository"]["repository"] == "MTDJDSP/MT-LIFT"
    assert manifest["dataset"]["acquired"] is False
    assert manifest["dataset"]["sha256"] is None
    assert manifest["license"]["status"] == "NO_EXPLICIT_LICENSE_FOUND"
    assert {attempt["outcome"] for attempt in manifest["access_attempts"]} == {
        "GOOGLE_ACCOUNT_SIGN_IN_HTML_NOT_DATASET",
        "PUBLIC_FILE_URL_NOT_RETRIEVABLE",
        "EXPIRED_OR_MISSING_ERRNO_MINUS_7",
        "REDIRECTED_TO_GOOGLE_SIGN_IN",
    }


def test_v10_qualification_is_outcome_isolated() -> None:
    result = verify_outcome_isolation()
    assert result["access_control"] == {
        "development_outcomes_opened": False,
        "freeze_created": False,
        "model_selection_performed": False,
        "reveal_started": False,
        "test_outcomes_opened": False,
    }


def test_v10_feature_timing_fails_closed() -> None:
    result = json.loads(QUALIFICATION_RESULT.read_text(encoding="utf-8"))
    assert result["feature_policy"]["allowlist"] == []
    assert result["feature_policy"]["f0_through_f98"] == "UNKNOWN_FORBIDDEN"
    assert result["documentation_findings"]["individual_feature_timestamps_documented"] is False


def test_v10_randomization_unit_and_repeat_structure_are_not_overclaimed() -> None:
    result = json.loads(QUALIFICATION_RESULT.read_text(encoding="utf-8"))
    findings = result["documentation_findings"]
    assert findings["randomized_coupon_assignment_documented"] is True
    assert findings["control_arm_zero_supported"] is True
    assert findings["randomization_unit_verified"] is False
    assert findings["repeat_users_auditable"] is False
    assert findings["assignment_probabilities_documented"] is False


def test_v10_stops_without_preregistration_freeze_or_test_artifacts() -> None:
    prohibited = {
        "V10_PREREGISTRATION.md",
        "V10_DEVELOPMENT_TOURNAMENT.md",
        "V10_PERSONALIZATION_GATE.md",
        "V10_FREEZE_MANIFEST.json",
        "V10_TEST_RESULT.json",
        "V10_VALIDATION_REPORT.md",
        "POST_REVEAL_QA.json",
    }
    assert not any((ROOT / name).exists() for name in prohibited)


def test_v10_claim_authority_and_status_fail_closed() -> None:
    result = verify_qualification_checkpoint()
    assert result["claim_authority"] == "NONE"
    assert result["qualified_for_causal_personalization"] is False
    assert result["final_status"] == "V10_DATASET_NOT_CAUSALLY_QUALIFIED"


def test_v10_reports_make_no_monetary_or_policy_result_claim() -> None:
    reports = [
        ROOT / "V10_RANDOMIZATION_AUDIT.md",
        ROOT / "V10_LIMITATIONS.md",
        ROOT / "V10_STOP_REPORT.md",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in reports)
    assert "no model or policy was fit" in joined.lower()
    assert "contribution profit" in joined.lower()
    assert "V10_MTLIFT_PERSONALIZATION_PROOF_PASS" not in joined


def test_v10_v8_and_v9_history_remains_immutable() -> None:
    verify_immutable_history()


def test_v10_package_contains_only_qualification_stage_outputs() -> None:
    allowed_suffixes = {".md", ".json", ".py"}
    files = [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    assert files
    assert all(path.suffix in allowed_suffixes for path in files)
    assert all(
        "RESULT" not in path.name or path.name == "V10_QUALIFICATION_RESULT.json"
        for path in files
    )


def test_v10_qualification_qa_records_repository_checks() -> None:
    qa = json.loads((ROOT / "V10_QUALIFICATION_QA.json").read_text(encoding="utf-8"))
    assert qa["final_status"] == "V10_DATASET_NOT_CAUSALLY_QUALIFIED"
    assert qa["checks"]["focused_pytest"]["status"] == "PASS"
    assert qa["checks"]["full_pytest"]["status"] == "PASS"
    assert qa["checks"]["ruff"]["status"] == "PASS"
    assert qa["checks"]["mypy"]["status"] == "PASS"
    assert qa["checks"]["outcome_isolation"] == "PASS"
