from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from commercial_twin.jdsearch_behavioral import (
    BEHAVIORAL_FEATURES,
    HORIZON_EVENTS,
    PURCHASE_ONLY_FEATURES,
    assert_purchase_only_is_clean,
    build_snapshot,
    event_times,
    support_groups,
    validate_row,
)


def fixture_row() -> tuple[list[str], list[str], list[str], list[str]]:
    types = ["CLICK", "CART", "ORD", "FLW", "CLICK", "ORD", "CART", "CLICK", "ORD", "FLW"]
    products = [str(index) for index in range(len(types))]
    queries = ["q", "q", "-1", "-1", "x", "x", "-1", "y", "y", "-1"]
    times = ["0"] + ["1"] * len(types)
    return types, products, queries, times


def test_event_clock_is_chronological_and_unit_agnostic() -> None:
    clock = event_times(["0", "2", "3", "4"], 3)
    assert clock.tolist() == [0.0, 2.0, 5.0]
    assert np.all(np.diff(clock) >= 0)


def test_misaligned_row_is_rejected() -> None:
    with pytest.raises(ValueError, match="aligned"):
        validate_row(["ORD"], ["1", "2"], ["q"], ["0", "1"])


def test_snapshot_uses_prefix_and_next_five_event_target() -> None:
    types, products, queries, times = fixture_row()
    row = build_snapshot(
        user_key=1,
        snapshot_index=0,
        cutoff=5,
        types=types,
        products=products,
        queries=queries,
        times=times,
    )
    assert row["ord_count_all"] == 1
    assert row["label_future_purchase"] == 1
    assert row["future_start_event"] == 5
    assert row["future_end_event"] == 5 + HORIZON_EVENTS


def test_future_change_cannot_change_features() -> None:
    types, products, queries, times = fixture_row()
    first = build_snapshot(
        user_key=1,
        snapshot_index=0,
        cutoff=5,
        types=types,
        products=products,
        queries=queries,
        times=times,
    )
    types[7:] = ["CART", "CART", "CART"]
    second = build_snapshot(
        user_key=1,
        snapshot_index=0,
        cutoff=5,
        types=types,
        products=products,
        queries=queries,
        times=times,
    )
    for feature in BEHAVIORAL_FEATURES:
        assert first[feature] == second[feature]


def test_purchase_only_has_no_behavioral_intent() -> None:
    assert_purchase_only_is_clean(PURCHASE_ONLY_FEATURES)
    assert any("cart" in item for item in BEHAVIORAL_FEATURES)
    assert any("query" in item for item in BEHAVIORAL_FEATURES)


def test_user_key_is_not_predictive_feature() -> None:
    assert "user_key" not in PURCHASE_ONLY_FEATURES
    assert "user_key" not in BEHAVIORAL_FEATURES


def test_behavior_rich_purchase_sparse_is_distinct() -> None:
    frame = pd.DataFrame({"ord_count_all": [1, 1, 6], "history_events": [10, 30, 30]})
    assert support_groups(frame).tolist() == [
        "PURCHASE_SPARSE_BEHAVIOR_SPARSE",
        "PURCHASE_SPARSE_BEHAVIOR_RICH",
        "PURCHASE_RICH_BEHAVIOR_RICH",
    ]
