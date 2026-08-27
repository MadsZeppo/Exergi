from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from commercial_twin.hm_day1 import (
    FEATURE_COLUMNS,
    HMPaths,
    HMWindow,
    ProbabilityCalibrator,
    assert_state_is_leak_safe,
    build_state_frame,
    prediction_metrics,
    select_model,
)


def fixture_paths(tmp_path: Path) -> HMPaths:
    transactions = pd.DataFrame(
        {
            "t_dat": pd.to_datetime(
                [
                    "2020-01-01", "2020-02-01", "2020-03-01",
                    "2020-04-01", "2020-04-15", "2020-05-01",
                ]
            ),
            "customer_id": pd.Series([1, 1, 2, 1, 3, 1], dtype="Int64"),
            "article_id": pd.Series([10, 11, 10, 12, 10, 10], dtype="Int64"),
            "price": [1.0, 2.0, 1.5, 3.0, 4.0, 9.0],
            "sales_channel_id": [1, 2, 1, 2, 1, 1],
        }
    )
    customers = pd.DataFrame(
        {
            "customer_id": pd.Series([1, 2, 3], dtype="Int64"),
            "FN": [1.0, np.nan, 1.0],
            "Active": [1.0, np.nan, 1.0],
            "club_member_status": ["ACTIVE", "PRE-CREATE", "ACTIVE"],
            "fashion_news_frequency": ["Regularly", "NONE", "Regularly"],
            "age": [30.0, np.nan, 40.0],
            "postal_code": ["a", "b", "c"],
        }
    )
    articles = pd.DataFrame(
        {
            "article_id": pd.Series([10, 11, 12], dtype="Int64"),
            "product_group_name": ["A", "B", "A"],
        }
    )
    t_path, c_path, a_path = (
        tmp_path / "transactions.parquet",
        tmp_path / "customers.parquet",
        tmp_path / "articles.parquet",
    )
    transactions.to_parquet(t_path, index=False)
    customers.to_parquet(c_path, index=False)
    articles.to_parquet(a_path, index=False)
    return HMPaths(t_path, c_path, a_path)


def test_state_excludes_as_of_and_target_window(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    frame = build_state_frame(
        paths,
        history_start=datetime(2020, 1, 1),
        as_of=datetime(2020, 4, 1),
        include_labels=True,
    )
    assert set(frame["customer_id"]) == {1, 2}
    customer = frame.set_index("customer_id").loc[1]
    assert customer["observation_count"] == 2
    assert customer["label_repeat"] == 1
    assert customer["label_lines"] == 1


def test_short_history_cannot_see_older_transactions(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    frame = build_state_frame(
        paths,
        history_start=datetime(2020, 2, 1),
        as_of=datetime(2020, 4, 1),
        include_labels=False,
    )
    customer = frame.set_index("customer_id").loc[1]
    assert customer["observation_count"] == 1
    assert pd.Timestamp(customer["first_seen"]) == pd.Timestamp("2020-02-01")


def test_future_new_customer_is_not_eligible(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    frame = build_state_frame(
        paths,
        history_start=datetime(2020, 1, 1),
        as_of=datetime(2020, 4, 1),
        include_labels=True,
    )
    assert 3 not in set(frame["customer_id"])


def test_label_interval_is_left_closed_right_open(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    frame = build_state_frame(
        paths,
        history_start=datetime(2020, 1, 1),
        as_of=datetime(2020, 4, 1),
        include_labels=True,
    )
    customer = frame.set_index("customer_id").loc[1]
    assert customer["label_repeat"] == 1
    assert customer["label_lines"] == 1  # May 1 is the right-open boundary and is excluded.


def test_state_guard_detects_old_or_future_data() -> None:
    frame = pd.DataFrame(
        {"first_seen": [pd.Timestamp("2019-01-01")], "last_seen": [pd.Timestamp("2020-01-01")]}
    )
    with pytest.raises(AssertionError, match="older"):
        assert_state_is_leak_safe(
            frame, history_start=datetime(2019, 6, 1), as_of=datetime(2020, 2, 1)
        )


def test_history_and_future_feasibility_guard() -> None:
    window = HMWindow(
        datetime(2020, 8, 23), 12, datetime(2019, 9, 7), datetime(2020, 9, 22)
    )
    with pytest.raises(ValueError, match="12m history unavailable"):
        window.validate()


def test_probability_calibrators_are_bounded() -> None:
    raw = np.array([0.1, 0.2, 0.8, 0.9])
    y = np.array([0, 0, 1, 1])
    for method in ("none", "platt", "isotonic"):
        output = ProbabilityCalibrator(method).fit(raw, y).transform(raw)
        assert np.all((output >= 0) & (output <= 1))


def test_expected_buyers_equals_sum_of_probabilities() -> None:
    y = np.array([0, 1, 0, 1])
    probability = np.array([0.1, 0.8, 0.2, 0.7])
    metrics = prediction_metrics(y, probability)
    assert metrics["repeat_buyers_predicted"] == pytest.approx(probability.sum())


def test_model_selection_never_accepts_test_metrics() -> None:
    frame = pd.DataFrame(
        [
            {"model": "a", "calibration": "none", "cutoff": f"c{i}", "ece": 0.01,
             "brier": 0.1, "buyer_count_error": 0.1, "auroc": 0.8}
            for i in range(3)
        ]
        + [
            {"model": "b", "calibration": "none", "cutoff": f"c{i}", "ece": 0.02,
             "brier": 0.2, "buyer_count_error": 0.1, "auroc": 0.9}
            for i in range(3)
        ]
    )
    selected = select_model(frame)
    assert selected["model"] == "a"
    assert selected["test_metrics_used_for_selection"] is False


def test_customer_id_is_not_a_predictive_feature() -> None:
    assert "customer_id" not in FEATURE_COLUMNS


def test_feature_names_do_not_claim_orders_aov_or_profit() -> None:
    forbidden = ("order", "aov", "profit")
    assert not any(token in feature for feature in FEATURE_COLUMNS for token in forbidden)
