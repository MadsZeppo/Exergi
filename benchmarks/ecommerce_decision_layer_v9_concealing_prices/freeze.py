"""Create the immutable V9 pre-validation policy freeze."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .integrity import (
    CONFIG,
    DEVELOPMENT_RESULT,
    FREEZE_MANIFEST,
    PRE_REVEAL_QA,
    SPLIT_MANIFEST,
    IntegrityError,
    assert_split_integrity,
    canonical_json_hash,
    git,
    load_json,
    sha256_file,
    source_hashes,
    source_tree_hash,
    verify_raw_hashes,
)


def create_freeze() -> dict[str, Any]:
    if FREEZE_MANIFEST.exists():
        raise IntegrityError("V9 freeze already exists and cannot be replaced")
    split = assert_split_integrity()
    raw_hashes = verify_raw_hashes()
    development = load_json(DEVELOPMENT_RESULT)
    qa = load_json(PRE_REVEAL_QA)
    if not qa.get("all_required_checks_passed", False):
        raise IntegrityError("V9 pre-reveal QA did not pass")
    expected = {"study1": "TEST_DELAYED_PRICE", "study3": "AVOID_DELAYED_PRICE"}
    observed = {name: development[name]["selection"] for name in expected}
    if observed != expected:
        raise IntegrityError(f"development policy mismatch: {observed}")
    config = load_json(CONFIG)
    hashes = source_hashes()
    freeze: dict[str, Any] = {
        "schema_version": 1,
        "status": "V9_FROZEN_VALIDATION_NOT_OPENED",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "repository_pre_freeze_head": git("rev-parse", "HEAD"),
        "preregistration_commit": "4638172",
        "raw_sha256": raw_hashes,
        "split_manifest_sha256": sha256_file(SPLIT_MANIFEST),
        "split_manifest_canonical_sha256": split["canonical_sha256"],
        "config_sha256": sha256_file(CONFIG),
        "config_canonical_sha256": canonical_json_hash(config),
        "development_result_sha256": sha256_file(DEVELOPMENT_RESULT),
        "pre_reveal_qa_sha256": sha256_file(PRE_REVEAL_QA),
        "source_tree_sha256": source_tree_hash(hashes),
        "frozen_source_files": hashes,
        "studies": {
            "study1": {
                "policy": "TEST_DELAYED_PRICE",
                "action": config["study1"]["action"],
                "reference": config["study1"]["reference"],
                "primary_outcome": config["study1"]["primary_outcome"],
                "estimand": config["study1"]["estimand"],
                "estimator": config["study1"]["estimator"],
                "claim_authority": "REAL_RANDOMIZED_AGGREGATE_REVENUE",
                "expected_validation_dates": 28,
                "expected_validation_rows": 56,
            },
            "study3": {
                "policy": "AVOID_DELAYED_PRICE",
                "action": config["study3"]["action"],
                "reference": config["study3"]["reference"],
                "primary_outcome": config["study3"]["primary_outcome"],
                "estimand": config["study3"]["estimand"],
                "estimator": config["study3"]["estimator"],
                "claim_authority": "REAL_RANDOMIZED_SALES_REVENUE",
                "expected_validation_rows": split["study3"]["row_counts"]["VALIDATION"],
                "expected_validation_arm_counts": split["study3"]["treatment_counts"][
                    "VALIDATION"
                ],
            },
        },
        "allowed_features": [],
        "prohibited_features": [
            "n_opens",
            "prob_sale",
            "units_sold",
            "revenues",
            "sessions",
            "bounce_rate",
        ],
        "random_seeds": config["random_seeds"],
        "validation_success_gate": config["validation_gate"],
        "action_cost": config["action_cost"],
        "validation_opened": False,
        "validation_consumed": False,
        "sealed_test_opened": False,
    }
    FREEZE_MANIFEST.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    return freeze


if __name__ == "__main__":
    print(json.dumps(create_freeze(), indent=2, sort_keys=True))
