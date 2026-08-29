from __future__ import annotations

import inspect
import json

from benchmarks.ecommerce_decision_layer_v9_concealing_prices import prepare
from benchmarks.ecommerce_decision_layer_v9_concealing_prices.integrity import (
    CONFIG,
    EXPECTED_RAW_SHA256,
    ROOT,
    SPLIT_MANIFEST,
    assert_split_integrity,
    verify_raw_hashes,
)


def test_v9_official_field_hashes_match() -> None:
    assert verify_raw_hashes() == EXPECTED_RAW_SHA256


def test_v9_split_is_disjoint_and_frozen_before_outcomes() -> None:
    manifest = assert_split_integrity()
    assert manifest["created_before_outcome_analysis"]
    assert manifest["study1"]["date_counts"] == {"DEVELOPMENT": 28, "VALIDATION": 28}
    assert manifest["study1"]["date_overlap_count"] == 0
    assert manifest["study3"]["hashed_id_overlap_count"] == 0
    assert sum(manifest["study3"]["row_counts"].values()) == 771_583


def test_v9_split_builder_is_outcome_isolated() -> None:
    source = inspect.getsource(prepare.build_split_manifest)
    for prohibited in ("revenues", "units_sold", "prob_sale", "n_opens"):
        assert prohibited not in source
    assert '{"date_id", "treatment"}' in source
    assert '{"user_id", "treatment"}' in source


def test_v9_timing_dictionary_forbids_post_treatment_features() -> None:
    timing = json.loads((ROOT / "V9_VARIABLE_TIMING_DICTIONARY.json").read_text())
    assert timing["field_studies"]["study3"]["n_opens"]["classification"] == (
        "POST_TREATMENT_FORBIDDEN"
    )
    assert timing["field_studies"]["study3"]["revenues"]["classification"] == "OUTCOME_ONLY"
    assert timing["field_studies"]["study1"]["users"]["classification"] == "EVALUATOR_ONLY"
    assert timing["personalization_allowed"] is False


def test_v9_config_has_no_invented_cost_or_sealed_fallback() -> None:
    config = json.loads(CONFIG.read_text())
    assert config["action_cost"]["known"] is False
    assert config["validation_gate"]["sealed_fallback"] is False
    assert config["personalization"]["allowed"] is False


def test_v9_split_manifest_persists_no_raw_ids() -> None:
    source = SPLIT_MANIFEST.read_text()
    manifest = json.loads(source)
    assert manifest["study3"]["raw_ids_persisted"] is False
    assert "unit_hashes" not in source
