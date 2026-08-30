from __future__ import annotations

import json

from benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.qualification import (
    QUALIFICATION_RESULT,
)
from benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.split import (
    SPLIT_MANIFEST,
    assignment_for,
    build_manifest,
    split_ids,
)


def test_v13_participant_hash_split_is_disjoint_complete_and_deterministic() -> None:
    development, validation = split_ids()
    assert not development & validation
    assert len(development | validation) == 15_134
    assert build_manifest() == build_manifest()


def test_v13_split_manifest_matches_frozen_algorithm() -> None:
    persisted = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    assert persisted == build_manifest()
    assert persisted["validation_outcomes_opened"] is False


def test_v13_hash_assignment_has_only_development_or_validation() -> None:
    development, validation = split_ids()
    assert {assignment_for(recid) for recid in development | validation} == {
        "DEVELOPMENT",
        "VALIDATION",
    }


def test_v13_preregistration_was_created_after_qualification() -> None:
    qualification = json.loads(QUALIFICATION_RESULT.read_text(encoding="utf-8"))
    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    assert qualification["access_control"]["raw_outcome_values_analyzed"] is False
    assert manifest["source_qualification_commit"] == (
        "47f46a3594493dd8febc614d011d9bda0564d64c"
    )
