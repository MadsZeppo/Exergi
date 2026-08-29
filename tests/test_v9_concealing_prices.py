from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from benchmarks.ecommerce_decision_layer_v9_concealing_prices import development, prepare
from benchmarks.ecommerce_decision_layer_v9_concealing_prices.estimators import (
    difference_in_means,
    paired_difference,
)
from benchmarks.ecommerce_decision_layer_v9_concealing_prices.integrity import (
    CONFIG,
    EXPECTED_RAW_SHA256,
    ROOT,
    SPLIT_MANIFEST,
    assert_split_integrity,
    verify_raw_hashes,
)
from benchmarks.ecommerce_decision_layer_v9_concealing_prices.validation_runner import (
    OneShotFiles,
    begin_reveal,
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


def test_v9_design_based_estimators_match_hand_calculation() -> None:
    outcome = np.array([1.0, 3.0, 4.0, 8.0])
    treatment = np.array([0, 0, 1, 1])
    estimate = difference_in_means(outcome, treatment)
    assert estimate.point == pytest.approx(4.0)
    assert estimate.lower_95 < estimate.point < estimate.upper_95
    paired = paired_difference(np.array([1.0, 2.0, 3.0, 4.0]))
    assert paired.point == pytest.approx(2.5)


def test_v9_development_loader_has_no_validation_or_sealed_argument() -> None:
    assert set(inspect.signature(development.load_study3_development).parameters) == set()
    source = inspect.getsource(development.analyze_development)
    assert "load_study3_validation" not in source
    assert "SEALED_TEST" not in source


def test_v9_static_selection_rule_is_symmetric_and_never_calls_development_act() -> None:
    positive = difference_in_means(np.array([0.0, 0.0, 2.0, 2.0]), np.array([0, 0, 1, 1]))
    negative = difference_in_means(np.array([2.0, 2.0, 0.0, 0.0]), np.array([0, 0, 1, 1]))
    assert development._selection(positive) == "TEST_DELAYED_PRICE"
    assert development._selection(negative) == "AVOID_DELAYED_PRICE"
    assert "ACT_DELAYED_PRICE" not in inspect.getsource(development._selection)


def test_v9_reveal_start_is_irreversible(tmp_path) -> None:
    files = OneShotFiles(
        reveal_start=tmp_path / "start.json",
        result=tmp_path / "result.json",
        consumed=tmp_path / "consumed.json",
        sufficient_statistics=tmp_path / "stats.json",
    )
    begin_reveal(files, {"study": "fixture"})
    assert files.reveal_start.exists()
    with pytest.raises(RuntimeError, match="already been consumed"):
        begin_reveal(files, {"study": "fixture"})


def test_v9_validation_runner_has_no_split_selector_or_sealed_loader() -> None:
    source = (ROOT / "validation_runner.py").read_text()
    assert "--split" not in source
    assert "load_study3_sealed" not in source
    assert "reveal_sealed" not in source
    assert "fallback" not in inspect.getsource(development.analyze_development).lower()
