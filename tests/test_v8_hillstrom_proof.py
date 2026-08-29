from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.integrity as integrity_module
import benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.validation_runner as runner_module
from benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.development_reconstruction import (
    reconstruct,
)
from benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.estimators import (
    arm_stratified_bootstrap,
    cross_fitted_aipw,
    difference_in_means,
    encode_pretreatment_features,
    lin_ancova,
    permutation_p_value,
    winsorized_difference,
)
from benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.integrity import (
    EXPECTED_ARMS,
    EXPECTED_RAW_SHA256,
    EXPECTED_ROWS,
    EXPECTED_VALIDATION_IDS_SHA256,
    MANIFEST,
    RAW,
    ROOT,
    IntegrityError,
    audit_pre_reveal,
    hash_id_manifest,
    sha256_file,
    verify_frozen_sources,
)
from benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.report import (
    ALLOWED_AUTHORITY,
    authorize_claim,
    render_claim_card,
)
from benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.validation_runner import (
    OneShotFiles,
    analyze_validation,
    begin_reveal,
)
from decision_engine.economic_policy_v72.splits import stable_unit_hash


def test_integrity_manifest_is_disjoint_and_matches_frozen_counts() -> None:
    manifest = json.loads(MANIFEST.read_text())
    hashes = {split: set(values) for split, values in manifest["unit_hashes"].items()}
    assert manifest["row_counts"] == EXPECTED_ROWS
    assert manifest["treatment_counts"] == EXPECTED_ARMS
    assert hashes["DEVELOPMENT"].isdisjoint(hashes["VALIDATION"])
    assert hashes["DEVELOPMENT"].isdisjoint(hashes["SEALED_TEST"])
    assert hashes["VALIDATION"].isdisjoint(hashes["SEALED_TEST"])
    assert hash_id_manifest(manifest["unit_hashes"]["VALIDATION"]) == EXPECTED_VALIDATION_IDS_SHA256


def test_row_zero_remains_only_in_quarantined_sealed_split() -> None:
    manifest = json.loads(MANIFEST.read_text())
    row_zero = stable_unit_hash("hillstrom", "row-0")
    assert row_zero in manifest["unit_hashes"]["SEALED_TEST"]
    assert row_zero not in manifest["unit_hashes"]["DEVELOPMENT"]
    assert row_zero not in manifest["unit_hashes"]["VALIDATION"]


def test_raw_checksum_matches_and_validation_is_still_unconsumed_pre_reveal() -> None:
    assert sha256_file(RAW) == EXPECTED_RAW_SHA256
    report = audit_pre_reveal()
    assert report.passed
    assert report.validation_materialization_absent
    assert report.validation_result_absent
    assert not report.sealed_fully_untouched


def test_development_reconstruction_reads_no_heldout_path() -> None:
    source = inspect.getsource(reconstruct)
    assert "parse_validation_rows" not in source
    assert "SEALED_TEST" not in source
    assert "VALIDATION_RESULT" not in source


def test_freeze_is_development_only_and_cannot_be_created_from_validation() -> None:
    source = Path("benchmarks/ecommerce_decision_layer_v8_hillstrom_proof/freeze.py").read_text()
    assert "parse_validation_rows" not in source
    assert "VALIDATION_RESULT" not in source
    assert "SEALED_TEST" not in source


def test_estimator_contract_has_no_oracle_or_evaluator_input() -> None:
    for estimator in (difference_in_means, lin_ancova, cross_fitted_aipw):
        parameters = inspect.signature(estimator).parameters
        assert not any("oracle" in name or "truth" in name for name in parameters)


@pytest.mark.parametrize("feature", ["visit", "conversion", "spend", "segment"])
def test_post_treatment_and_outcome_features_are_frozen_as_prohibited(feature: str) -> None:
    config = json.loads((ROOT / "FROZEN_ANALYSIS_CONFIG.json").read_text())
    assert feature in config["prohibited_feature_columns"]
    assert feature not in config["allowed_feature_columns"]


def test_raw_difference_and_neyman_se_match_hand_calculation() -> None:
    spend = np.array([0.0, 2.0, 1.0, 5.0])
    treatment = np.array([0, 0, 1, 1])
    result = difference_in_means(spend, treatment, 0.05)
    treated = np.array([0.95, 4.95])
    control = np.array([0.0, 2.0])
    expected_point = treated.mean() - control.mean()
    expected_se = np.sqrt(treated.var(ddof=1) / 2 + control.var(ddof=1) / 2)
    assert result.point == pytest.approx(expected_point)
    assert result.standard_error == pytest.approx(expected_se)


def test_email_cost_is_subtracted_once_and_zero_spend_is_preserved() -> None:
    spend = np.array([0.0, 0.0, 1.0, 1.0])
    treatment = np.array([0, 1, 0, 1])
    gross = difference_in_means(spend, treatment, 0.0)
    net = difference_in_means(spend, treatment, 0.05)
    assert len(spend) == 4
    assert gross.point == pytest.approx(0.0)
    assert net.point == pytest.approx(-0.05)


def test_lin_ancova_recovers_fixture_effect_with_interactions() -> None:
    rng = np.random.default_rng(801)
    n = 3000
    treatment = np.tile(np.array([0, 1]), n // 2)
    x = rng.normal(size=(n, 3))
    spend = 4.0 + x[:, 0] + treatment * (1.2 + 0.4 * x[:, 1]) + rng.normal(0, 0.3, n)
    result = lin_ancova(spend, treatment, x, 0.05)
    assert result.point == pytest.approx(1.15, abs=0.04)
    assert result.lower_95 < result.point < result.upper_95


def test_aipw_is_deterministic_cross_fitted_and_uses_known_propensity() -> None:
    rng = np.random.default_rng(802)
    n = 2000
    treatment = np.tile(np.array([0, 1]), n // 2)
    x = rng.normal(size=(n, 4))
    spend = 5 + x[:, 0] + 0.8 * treatment + rng.normal(0, 0.5, n)
    hashes = np.asarray([f"unit-{index}" for index in range(n)])
    first = cross_fitted_aipw(
        spend, treatment, x, hashes, 0.05, folds=5, seed=77, ridge_alpha=10, propensity=0.5
    )
    second = cross_fitted_aipw(
        spend, treatment, x, hashes, 0.05, folds=5, seed=77, ridge_alpha=10, propensity=0.5
    )
    assert first[0] == second[0]
    np.testing.assert_array_equal(first[1], second[1])
    assert set(first[2]) == set(range(5))
    assert first[0].point == pytest.approx(0.75, abs=0.06)


def test_permutation_and_arm_bootstrap_are_reproducible() -> None:
    rng = np.random.default_rng(803)
    treatment = np.repeat(np.array([0, 1]), 200)
    spend = rng.normal(5 + treatment * 0.5, 1.0)
    first_p = permutation_p_value(spend, treatment, 0.05, replicates=200, seed=91)
    second_p = permutation_p_value(spend, treatment, 0.05, replicates=200, seed=91)
    first_b, first_values = arm_stratified_bootstrap(
        spend, treatment, 0.05, replicates=200, seed=92
    )
    second_b, second_values = arm_stratified_bootstrap(
        spend, treatment, 0.05, replicates=200, seed=92
    )
    assert first_p == second_p
    assert first_b == second_b
    np.testing.assert_array_equal(first_values, second_values)
    assert first_b.lower_95 <= first_b.point <= first_b.upper_95


def test_nonzero_winsorization_rejects_degenerate_zero_cap() -> None:
    with pytest.raises(ValueError, match="positive"):
        winsorized_difference(np.array([0.0, 2.0]), np.array([0, 1]), 0.05, 0.0)


def test_feature_encoder_uses_exact_eight_pretreatment_fields_and_frozen_levels() -> None:
    frame = pd.DataFrame(
        {
            "recency": [1, 2],
            "history": [10, 20],
            "mens": [0, 1],
            "womens": [1, 0],
            "newbie": [0, 1],
            "history_segment": ["a", "b"],
            "zip_code": ["r", "u"],
            "channel": ["w", "p"],
        }
    )
    encoded, levels, names = encode_pretreatment_features(frame)
    second, _, second_names = encode_pretreatment_features(frame, levels)
    np.testing.assert_array_equal(encoded, second)
    assert names == second_names
    assert encoded.shape[0] == 2


def test_one_shot_start_is_permanent_even_without_result(tmp_path: Path) -> None:
    files = OneShotFiles(tmp_path / "start.json", tmp_path / "result.json", tmp_path / "done.json")
    authorization = begin_reveal(files, {"test": True})
    assert authorization.reveal_start.exists()
    with pytest.raises(IntegrityError, match="already been consumed"):
        begin_reveal(files, {"test": True})


def test_validation_run_is_rejected_without_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_module, "FREEZE_MANIFEST", tmp_path / "missing.json")
    with pytest.raises(IntegrityError, match="requires a freeze"):
        runner_module.dry_run()


def test_frozen_source_or_config_mutation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(integrity_module, "source_hashes", lambda: {"config": "mutated"})
    with pytest.raises(IntegrityError, match="source/config mutation"):
        verify_frozen_sources(
            {
                "frozen_source_files": {"config": "frozen"},
                "source_tree_sha256": "unused",
                "split_manifest_sha256": "unused",
                "quarantine_record_sha256": "unused",
                "pre_reveal_qa_sha256": "unused",
            }
        )


def test_split_mutation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    hashes = {"source": "same"}
    tree_hash = integrity_module.canonical_json_hash(hashes)
    monkeypatch.setattr(integrity_module, "source_hashes", lambda: hashes)
    monkeypatch.setattr(integrity_module, "source_tree_hash", lambda _: tree_hash)
    monkeypatch.setattr(integrity_module, "sha256_file", lambda _: "mutated")
    with pytest.raises(IntegrityError, match="split manifest mutation"):
        verify_frozen_sources(
            {
                "frozen_source_files": hashes,
                "source_tree_sha256": tree_hash,
                "split_manifest_sha256": "frozen",
                "quarantine_record_sha256": "frozen",
                "pre_reveal_qa_sha256": "frozen",
            }
        )


def test_validation_runner_has_no_split_selector_or_sealed_fallback() -> None:
    source = Path(
        "benchmarks/ecommerce_decision_layer_v8_hillstrom_proof/validation_runner.py"
    ).read_text()
    assert "--split" not in source
    assert "parse_sealed" not in source
    assert "sealed_test.parquet" not in source.lower()
    assert "Womens E-Mail fallback" not in source


def test_report_regeneration_has_no_raw_data_access() -> None:
    source = Path("benchmarks/ecommerce_decision_layer_v8_hillstrom_proof/report.py").read_text()
    assert "data/raw" not in source
    assert "parse_validation_rows" not in source


def test_claim_boundaries_fail_closed() -> None:
    assert authorize_claim(ALLOWED_AUTHORITY, "PASS") == ALLOWED_AUTHORITY
    for claim in ("contribution_profit", "personalization_proven", "production_ready"):
        with pytest.raises(ValueError, match="prohibited"):
            authorize_claim(claim, "PASS")
    with pytest.raises(ValueError, match="requires PASS"):
        authorize_claim(ALLOWED_AUTHORITY, "FAIL")


def test_failure_claim_card_does_not_issue_positive_authority() -> None:
    card = render_claim_card(
        {"verdict": "FAIL", "claim_authority": ALLOWED_AUTHORITY, "claim_text": "unused"}
    )
    assert "remains shadow-only" in card
    assert "contribution profit" in card


def test_total_incremental_value_uses_the_full_primary_population() -> None:
    frame = pd.DataFrame(
        {
            "unit_hash": [f"u-{index}" for index in range(40)],
            "segment": ["No E-Mail"] * 20 + ["Mens E-Mail"] * 20,
            "spend": [1.0] * 20 + [2.0] * 20,
            "recency": [1] * 40,
            "history": [10] * 40,
            "mens": [0] * 40,
            "womens": [0] * 40,
            "newbie": [0] * 40,
            "history_segment": ["a"] * 40,
            "zip_code": ["u"] * 40,
            "channel": ["w"] * 40,
        }
    )
    config = json.loads((ROOT / "FROZEN_ANALYSIS_CONFIG.json").read_text())
    config["permutation"]["replicates"] = 50
    config["bootstrap"]["replicates"] = 50
    development = {
        "category_levels": {"history_segment": ["a"], "zip_code": ["u"], "channel": ["w"]}
    }
    result = analyze_validation(frame, config, development)
    assert result["primary"]["point"] == pytest.approx(0.95)
    assert result["primary"]["total_incremental_value"] == pytest.approx(38.0)
