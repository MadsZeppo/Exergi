from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from decision_engine.forecasting.baseline import BaselineKind, SeasonalBaseline


def test_four_week_weekday_baseline() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    history = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(28)],
            "outcome": np.tile(np.arange(7), 4),
        }
    )
    assert np.array_equal(
        SeasonalBaseline(BaselineKind.FOUR_WEEK_WEEKDAY).predict(history, 7), np.arange(7)
    )
