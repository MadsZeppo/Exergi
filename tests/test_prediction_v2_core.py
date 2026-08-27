from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from commercial_twin.prediction_v2.core import (
    AggregateCandidate,
    FinalRunGuard,
    HierarchicalRateModel,
    PredictionV2Output,
    SparseRouter,
    SupportClass,
    SupportThresholds,
    apply_group_logit_adjustments,
    calibration_in_the_large,
    classify_support,
    empirical_reliability,
    logit_shift_reconcile,
    select_aggregate_candidate,
    select_safe_v2_cutoffs,
)


def test_support_router_is_deterministic() -> None:
    args = (np.array([1, 2, 4, 9]), np.array([1, 3, 8, 25]), np.array([10, 40, 100, 300]))
    first = classify_support(*args)
    second = classify_support(*args)
    assert np.array_equal(first, second)
    assert first.tolist() == ["VERY_SPARSE", "SPARSE", "ESTABLISHED", "RICH"]


def test_support_thresholds_are_explicit() -> None:
    thresholds = SupportThresholds(established_active_days=5)
    output = classify_support(np.array([4]), np.array([10]), np.array([100]), thresholds)
    assert output[0] == SupportClass.SPARSE.value


def test_hierarchical_model_shrinks_small_groups() -> None:
    frame = pd.DataFrame(
        {
            "support_class": ["SPARSE"] * 10 + ["RICH"] * 1000,
            "lifecycle": ["NEW"] * 10 + ["ACTIVE"] * 1000,
            "dominant_channel": ["1"] * 1010,
            "label_repeat": [1] * 10 + [0, 1] * 500,
        }
    )
    model = HierarchicalRateModel(prior_strength=100, minimum_group_support=1).fit(frame)
    probability, _ = model.predict(frame.iloc[:1])
    assert 0.5 < probability[0] < 1.0


def test_hierarchical_model_disables_unsupported_leaf() -> None:
    train = pd.DataFrame(
        {
            "support_class": ["SPARSE"] * 10,
            "lifecycle": ["NEW"] * 10,
            "dominant_channel": ["1"] * 10,
            "label_repeat": [0, 1] * 5,
        }
    )
    model = HierarchicalRateModel(minimum_group_support=200).fit(train)
    probability, support = model.predict(train.iloc[:1])
    assert probability[0] == pytest.approx(0.5)
    assert support[0] == 0


def test_sparse_router_uses_hierarchy_only_for_sparse() -> None:
    probability, route = SparseRouter().route(
        ["SPARSE", "RICH"], np.array([0.9, 0.8]), np.array([0.2, 0.3])
    )
    assert probability.tolist() == [0.2, 0.8]
    assert route.tolist() == ["HIERARCHICAL_PRIOR", "ESTABLISHED_RANKER"]


def test_reconciliation_matches_target_and_is_bounded() -> None:
    probability = np.array([0.1, 0.2, 0.7, 0.9])
    reconciled, _ = logit_shift_reconcile(probability, 2.5)
    assert reconciled.sum() == pytest.approx(2.5, abs=1e-6)
    assert np.all((reconciled >= 0) & (reconciled <= 1))


def test_reconciliation_preserves_ranking() -> None:
    probability = np.array([0.4, 0.1, 0.8, 0.3])
    reconciled, _ = logit_shift_reconcile(probability, 1.2)
    assert np.array_equal(np.argsort(probability), np.argsort(reconciled))


def test_reconciliation_rejects_invalid_target() -> None:
    with pytest.raises(ValueError, match="target buyers"):
        logit_shift_reconcile(np.array([0.1, 0.2]), 3)


def test_group_adjustment_requires_support() -> None:
    raw = np.array([0.2, 0.2])
    adjusted = apply_group_logit_adjustments(
        raw, ["a", "b"], {"a": (1.0, 1000), "b": (1.0, 10)}, minimum_support=100
    )
    assert adjusted[0] > raw[0]
    assert adjusted[1] == pytest.approx(raw[1])


def test_aggregate_selection_uses_error_worst_window_then_bias() -> None:
    winner = select_aggregate_candidate(
        [
            AggregateCandidate("unstable", (0.01, 0.30), (0.01, -0.30)),
            AggregateCandidate("stable", (0.12, 0.12), (0.02, 0.02)),
        ]
    )
    assert winner.name == "stable"


def test_cutoff_requires_full_twelve_month_history() -> None:
    result = select_safe_v2_cutoffs(date(2018, 9, 20), date(2020, 9, 22))
    assert all(date.fromisoformat(item) >= date(2019, 9, 20) for item in result["candidates"])


def test_old_v1_final_is_never_selected() -> None:
    result = select_safe_v2_cutoffs(date(2018, 9, 20), date(2020, 9, 22))
    assert result["official_final"] != "2020-08-24"


def test_v2_final_target_does_not_overlap_v1_targets() -> None:
    result = select_safe_v2_cutoffs(date(2018, 9, 20), date(2020, 9, 22))
    final = date.fromisoformat(result["official_final"])
    assert final <= date(2020, 5, 9)  # Half-open 30d window ends at first exposed cutoff.


def test_final_guard_requires_predictions_before_reveal(tmp_path: Path) -> None:
    guard = FinalRunGuard(tmp_path)
    guard.freeze({"final": "frozen"})
    with pytest.raises(RuntimeError, match="predictions"):
        guard.require_predictions_before_reveal()


def test_official_final_cannot_run_twice(tmp_path: Path) -> None:
    guard = FinalRunGuard(tmp_path)
    guard.freeze({"final": "frozen"})
    guard.predictions_path.write_bytes(b"frozen")
    guard.mark_evaluated({"status": "revealed"})
    with pytest.raises(RuntimeError, match="only once"):
        guard.require_predictions_before_reveal()


def test_prediction_output_bounds_probability() -> None:
    with pytest.raises(ValueError, match="probabilities"):
        PredictionV2Output("x", 1.0, 0.2, 1.2, "ranker", SupportClass.RICH, "HIGH", "ACTIVE", "v1")


def test_expected_buyers_are_sum_of_final_probabilities() -> None:
    final_probability = np.array([0.2, 0.4, 0.8])
    assert float(final_probability.sum()) == pytest.approx(1.4)


def test_customer_identifier_is_not_a_v2_model_input() -> None:
    allowed = {"rank_score", "support_class", "lifecycle", "dominant_channel"}
    assert "customer_id" not in allowed


def test_reliability_fails_closed_for_sparse_or_bad_calibration() -> None:
    reliability = empirical_reliability(
        ["SPARSE", "RICH", "RICH"], [0.01, 0.10, 0.01], temporal_std=0.01
    )
    assert reliability.tolist() == ["LOW", "LOW", "HIGH"]


def test_calibration_in_the_large_is_zero_for_matching_rate() -> None:
    y = np.array([0, 1, 0, 1])
    probability = np.full(4, 0.5)
    assert calibration_in_the_large(y, probability) == pytest.approx(0.0)


def test_v2_language_does_not_claim_orders_aov_or_profit() -> None:
    fields = PredictionV2Output.__dataclass_fields__
    assert not {"orders", "aov", "profit"}.intersection(fields)
