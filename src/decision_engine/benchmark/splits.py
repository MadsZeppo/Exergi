from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class TemporalSplit:
    train_start: date
    train_end: date
    decision_date: date
    outcome_end: date


def expanding_window_splits(
    start: date,
    end: date,
    *,
    min_train_days: int,
    horizon_days: int,
    step_days: int,
) -> list[TemporalSplit]:
    decision = start + timedelta(days=min_train_days)
    result: list[TemporalSplit] = []
    while decision + timedelta(days=horizon_days - 1) <= end:
        result.append(
            TemporalSplit(
                start,
                decision - timedelta(days=1),
                decision,
                decision + timedelta(days=horizon_days - 1),
            )
        )
        decision += timedelta(days=step_days)
    return result


def rolling_origin_splits(
    start: date,
    end: date,
    *,
    train_days: int,
    horizon_days: int,
    step_days: int,
) -> list[TemporalSplit]:
    expanding = expanding_window_splits(
        start, end, min_train_days=train_days, horizon_days=horizon_days, step_days=step_days
    )
    return [
        TemporalSplit(
            s.decision_date - timedelta(days=train_days),
            s.train_end,
            s.decision_date,
            s.outcome_end,
        )
        for s in expanding
    ]
