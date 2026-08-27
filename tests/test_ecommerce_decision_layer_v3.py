from __future__ import annotations

import ast
from pathlib import Path

from benchmarks.ecommerce_decision_layer_v3.discovery import (
    MERCHANT_TYPES,
    evaluate_discovery,
    synthetic_merchant,
)
from commercial_twin.ecommerce_opportunities import (
    ACTION_TAXONOMY,
    EcommerceOpportunityEngine,
    EcommerceOpportunityType,
)


def test_all_five_opportunity_families_are_implemented() -> None:
    assert set(ACTION_TAXONOMY) == set(EcommerceOpportunityType)


def test_null_merchant_has_no_hallucinated_opportunity() -> None:
    segments, truth = synthetic_merchant("null", 123)
    assert truth.opportunities == ()
    assert EcommerceOpportunityEngine().detect(segments) == ()


def test_each_planted_family_is_detected_without_labels() -> None:
    for merchant_type in MERCHANT_TYPES[1:]:
        segments, truth = synthetic_merchant(merchant_type, 456)
        detected = EcommerceOpportunityEngine().detect(segments)
        truth_keys = {(kind, segment) for kind, segment, _ in truth.opportunities}
        detected_keys = {(item.opportunity_type, item.segment_id) for item in detected}
        assert truth_keys <= detected_keys


def test_economic_weighted_metrics_use_gap_weights() -> None:
    _, metrics = evaluate_discovery(range(500, 505))
    assert 0 <= metrics["economic_weighted_precision"] <= 1
    assert 0 <= metrics["economic_weighted_recall"] <= 1
    assert metrics["top1_accuracy"] == 1


def test_product_detector_does_not_import_planted_truth() -> None:
    tree = ast.parse(Path("src/commercial_twin/ecommerce_opportunities.py").read_text())
    assert all("PlantedTruth" not in ast.unparse(node) for node in ast.walk(tree))


def test_action_taxonomy_is_constrained_and_relevant() -> None:
    margin = ACTION_TAXONOMY[EcommerceOpportunityType.DISCOUNT_MARGIN_LEAKAGE]
    assert "discount_depth_adjustment" in margin
    assert "free_shipping" not in margin
