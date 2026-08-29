"""Create the V8 immutable pre-validation analysis freeze."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .development_reconstruction import reconstruct
from .integrity import (
    BASE_CHECKPOINT,
    BUY_BAITS_LOCK,
    DEVELOPMENT,
    DEVELOPMENT_RESULT,
    EXPECTED_VALIDATION_IDS_SHA256,
    FREEZE_MANIFEST,
    MANIFEST,
    QA_RECORD,
    QUARANTINE,
    RAW,
    ROOT,
    IntegrityError,
    canonical_json_hash,
    current_head,
    require_pre_reveal_integrity,
    sha256_file,
    source_hashes,
    source_tree_hash,
)


def create_freeze() -> dict[str, Any]:
    if FREEZE_MANIFEST.exists():
        raise IntegrityError("V8 freeze already exists; it cannot be replaced")
    integrity = require_pre_reveal_integrity()
    if not QA_RECORD.exists():
        raise IntegrityError("PRE_REVEAL_QA.json must exist before freeze")
    qa = json.loads(QA_RECORD.read_text())
    if not qa.get("all_required_checks_passed", False):
        raise IntegrityError("pre-reveal QA is not green")
    development = reconstruct(write=True)
    config = json.loads((ROOT / "FROZEN_ANALYSIS_CONFIG.json").read_text())
    claim = json.loads((ROOT / "CLAIM_CONTRACT.json").read_text())
    hashes = source_hashes()
    freeze: dict[str, Any] = {
        "schema_version": 1,
        "status": "V8_FROZEN_VALIDATION_NOT_OPENED",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "repository_base_checkpoint": BASE_CHECKPOINT,
        "repository_pre_freeze_head": current_head(),
        "source_tree_sha256": source_tree_hash(hashes),
        "frozen_source_files": hashes,
        "raw_hillstrom_sha256": sha256_file(RAW),
        "split_manifest_sha256": sha256_file(MANIFEST),
        "quarantine_record_sha256": sha256_file(QUARANTINE),
        "buy_baits_lock_sha256": sha256_file(BUY_BAITS_LOCK),
        "development_materialization_sha256": sha256_file(DEVELOPMENT),
        "development_reconstruction_sha256": sha256_file(DEVELOPMENT_RESULT),
        "validation_hashed_id_manifest_sha256": EXPECTED_VALIDATION_IDS_SHA256,
        "config_sha256": sha256_file(ROOT / "FROZEN_ANALYSIS_CONFIG.json"),
        "config_canonical_sha256": canonical_json_hash(config),
        "claim_contract_sha256": sha256_file(ROOT / "CLAIM_CONTRACT.json"),
        "claim_contract_canonical_sha256": canonical_json_hash(claim),
        "preregistration_sha256": sha256_file(ROOT / "PREREGISTRATION.md"),
        "pre_reveal_qa_sha256": sha256_file(QA_RECORD),
        "policy": config["static_policy"],
        "outcome_definition": config["outcome"],
        "treatment_label": config["arm_labels"]["treatment"],
        "control_label": config["arm_labels"]["control"],
        "secondary_label": config["arm_labels"]["secondary"],
        "email_cost": config["email_cost"],
        "primary_estimator": config["primary"],
        "success_gate": {
            "integrity_gates_pass": True,
            "point_estimate_strictly_positive": True,
            "two_sided_95_lower_bound_strictly_positive": True,
            "otherwise": "FAIL unless integrity is broken, then INVALID",
        },
        "secondary_estimators": {
            "lin_ancova": "eight pretreatment features, interactions, HC3",
            "cross_fitted_aipw": config["aipw"],
            "randomization_inference": config["permutation"],
            "arm_stratified_bootstrap": config["bootstrap"],
            "heavy_tail": config["heavy_tail"],
        },
        "random_seeds": {
            "aipw": config["aipw"]["seed"],
            "permutation": config["permutation"]["seed"],
            "bootstrap": config["bootstrap"]["seed"],
        },
        "allowed_input_columns": [
            *config["allowed_feature_columns"],
            "segment",
            "spend",
        ],
        "prohibited_columns": config["prohibited_feature_columns"],
        "expected_validation_rows": config["expected_validation_rows"],
        "expected_validation_arm_counts": config["expected_validation_arm_counts"],
        "development_reconstruction_status": development["status"],
        "integrity": integrity.as_dict(),
        "validation_opened": False,
        "validation_consumed": False,
        "sealed_test_opened": False,
        "sealed_test_fully_untouched": False,
    }
    FREEZE_MANIFEST.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    return freeze


if __name__ == "__main__":
    print(json.dumps(create_freeze(), indent=2, sort_keys=True))
