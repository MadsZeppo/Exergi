from __future__ import annotations

from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.calibration import (
    EXPECTED,
    ROOT,
    calibration_statistics,
    verify_sources,
)


def test_v14_has_two_independent_read_only_hash_verified_backbones() -> None:
    result = verify_sources()
    assert result["qualified_backbones"] >= 2
    assert len({source["independence_group"] for source in result["sources"].values()}) >= 2
    for name, expected in EXPECTED.items():
        assert result["sources"][name]["sha256"] == expected["sha256"]
        assert result["sources"][name]["read_only"] is True


def test_v14_calibration_is_distributional_not_causal_truth() -> None:
    result = calibration_statistics()
    assert result["calibration_only_not_causal_truth"] is True
    assert result["completejourney"]["population"]["customer_count"] == 2_469
    assert result["online_retail_ii"]["population"]["line_count"] == 1_067_371
    assert "contribution_profit" in result["unsupported_calibrations"]
    assert result["completejourney"]["return_authority"] == "NO_AUTHORITATIVE_RETURN_FIELD"
    assert "CANCELLATION_PROXY" in result["online_retail_ii"]["return_authority"]


def test_v14_phase_one_has_no_synthetic_outcomes_or_causal_truth() -> None:
    artifact = (ROOT / "V14_REALITY_CALIBRATION.json").read_text(encoding="utf-8")
    assert '"synthetic_outcomes_generated": false' in artifact
    assert '"causal_truth_imported": false' in artifact
    assert '"cross_source_entities_joined": false' in artifact


def test_v14_calibration_qa_is_all_green() -> None:
    artifact = (ROOT / "V14_CALIBRATION_QA.json").read_text(encoding="utf-8")
    assert '"status": "PASS"' in artifact
    assert '"phase": "REALITY_CALIBRATION_ONLY"' in artifact
    assert "false" not in artifact
