"""State machine that makes reveal-before-lock structurally impossible."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

import polars as pl


class TimeMachineState(StrEnum):
    INITIAL = "INITIAL"
    FROZEN = "FROZEN"
    LOCKED = "LOCKED"
    REVEALED = "REVEALED"


class TimeMachineBenchmark:
    def __init__(
        self,
        data: pl.DataFrame,
        *,
        timestamp_col: str = "timestamp",
        observed_at_col: str = "observed_at",
    ) -> None:
        self._data = data.clone()
        self.timestamp_col = timestamp_col
        self.observed_at_col = observed_at_col
        self.state = TimeMachineState.INITIAL
        self.cutoff: datetime | None = None
        self._history: pl.DataFrame | None = None
        self._future: pl.DataFrame | None = None
        self._prediction: Any = None

    def freeze_at(self, cutoff: datetime) -> TimeMachineBenchmark:
        if self.state != TimeMachineState.INITIAL:
            raise RuntimeError("benchmark may only be frozen once")
        if (
            self.timestamp_col not in self._data.columns
            or self.observed_at_col not in self._data.columns
        ):
            raise ValueError("timestamp and observed_at columns are required")
        # A row is usable only when both its event and recorded availability
        # precede decision time.
        available = (pl.col(self.timestamp_col) < cutoff) & (pl.col(self.observed_at_col) <= cutoff)
        self._history = self._data.filter(available).clone()
        self._future = self._data.filter(pl.col(self.timestamp_col) >= cutoff).clone()
        if self._history.height:
            latest_event = self._history[self.timestamp_col].max()
            latest_observation = self._history[self.observed_at_col].max()
            assert isinstance(latest_event, datetime) and latest_event < cutoff
            assert isinstance(latest_observation, datetime) and latest_observation <= cutoff
        self.cutoff = cutoff
        self.state = TimeMachineState.FROZEN
        return self

    def history(self) -> pl.DataFrame:
        if self.state not in {TimeMachineState.FROZEN, TimeMachineState.LOCKED}:
            raise RuntimeError("history is available only after freeze and before reveal")
        assert self._history is not None
        return self._history.clone()

    def lock_prediction(
        self, prediction: Any, persist: Callable[[Any], None] | None = None
    ) -> None:
        if self.state != TimeMachineState.FROZEN:
            raise RuntimeError("prediction can only be locked after freeze")
        if persist is not None:
            persist(prediction)  # persistence must succeed before transition
        self._prediction = prediction
        self.state = TimeMachineState.LOCKED

    def reveal_outcome(self, *, start: datetime, end: datetime) -> pl.DataFrame:
        if self.state != TimeMachineState.LOCKED:
            raise RuntimeError("outcome cannot be revealed before prediction is locked")
        assert self._future is not None and self.cutoff is not None
        if start < self.cutoff or end < start:
            raise ValueError("invalid outcome window")
        self.state = TimeMachineState.REVEALED
        return self._future.filter(
            (pl.col(self.timestamp_col) >= start) & (pl.col(self.timestamp_col) <= end)
        ).clone()

    @property
    def locked_prediction(self) -> Any:
        if self.state == TimeMachineState.INITIAL:
            raise RuntimeError("no prediction")
        return self._prediction
