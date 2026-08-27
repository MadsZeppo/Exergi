from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from decision_engine.benchmark.time_machine import TimeMachineBenchmark
from decision_engine.features.leakage import assert_training_precedes_decision
from decision_engine.features.temporal import add_leak_safe_temporal_features


def frame() -> pl.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    times = [start + timedelta(days=i) for i in range(10)]
    return pl.DataFrame(
        {
            "timestamp": times,
            "observed_at": times,
            "entity_id": ["a"] * 10,
            "outcome": list(range(10)),
        }
    )


def test_freeze_excludes_cutoff_and_future() -> None:
    cutoff = datetime(2024, 1, 6, tzinfo=UTC)
    history = TimeMachineBenchmark(frame()).freeze_at(cutoff).history()
    assert history.height == 5
    assert_training_precedes_decision(history, cutoff)


def test_observed_late_is_excluded() -> None:
    data = frame().with_columns(
        pl.when(pl.col("outcome") == 2)
        .then(pl.datetime(2025, 1, 1, time_zone="UTC"))
        .otherwise(pl.col("observed_at"))
        .alias("observed_at")
    )
    history = TimeMachineBenchmark(data).freeze_at(datetime(2024, 1, 6, tzinfo=UTC)).history()
    assert 2 not in history["outcome"].to_list()


def test_rolling_features_shift_before_rolling() -> None:
    featured = add_leak_safe_temporal_features(frame(), lags=(1,), windows=(3,))
    assert featured["outcome_lag_1"].to_list()[4] == 3
    assert featured["rolling_mean_3"].to_list()[4] == pytest.approx(2.0)
