from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from decision_engine.benchmark.time_machine import TimeMachineBenchmark, TimeMachineState


def test_reveal_requires_locked_prediction() -> None:
    cutoff = datetime(2024, 1, 2, tzinfo=UTC)
    data = pl.DataFrame(
        {
            "timestamp": [cutoff - timedelta(days=1), cutoff],
            "observed_at": [cutoff - timedelta(days=1), cutoff],
            "outcome": [1, 2],
        }
    )
    benchmark = TimeMachineBenchmark(data).freeze_at(cutoff)
    with pytest.raises(RuntimeError, match="before prediction"):
        benchmark.reveal_outcome(start=cutoff, end=cutoff)
    benchmark.lock_prediction({"value": 1})
    assert benchmark.reveal_outcome(start=cutoff, end=cutoff)["outcome"].item() == 2
    assert benchmark.state == TimeMachineState.REVEALED
