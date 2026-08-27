from __future__ import annotations

from enum import StrEnum

import numpy as np
import polars as pl


class BaselineKind(StrEnum):
    LAST = "last_observation"
    PREVIOUS_WEEKDAY = "same_weekday_previous_week"
    FOUR_WEEK_WEEKDAY = "mean_same_weekday_previous_4_weeks"
    SEASONAL_MOVING_AVERAGE = "seasonal_moving_average"


class SeasonalBaseline:
    def __init__(self, kind: BaselineKind = BaselineKind.FOUR_WEEK_WEEKDAY) -> None:
        self.kind = kind

    def predict(
        self, history: pl.DataFrame, horizon: int, target_col: str = "outcome"
    ) -> np.ndarray:
        values = history.sort("timestamp")[target_col].to_numpy().astype(float)
        if values.size == 0:
            raise ValueError("baseline needs non-empty history")
        if self.kind == BaselineKind.LAST:
            return np.repeat(values[-1], horizon)
        if self.kind == BaselineKind.PREVIOUS_WEEKDAY:
            pattern = values[-7:] if values.size >= 7 else values
        elif self.kind == BaselineKind.FOUR_WEEK_WEEKDAY:
            if values.size < 7:
                pattern = values
            else:
                weeks = min(4, values.size // 7)
                matrix = values[-weeks * 7 :].reshape(weeks, 7)
                pattern = matrix.mean(axis=0)
        else:
            pattern = values[-min(28, values.size) :]
        return np.resize(pattern, horizon)
