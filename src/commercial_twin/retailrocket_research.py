"""Leak-separated calendar-time snapshots for the RetailRocket benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

EVENTS = ("view", "addtocart", "transaction")
HORIZONS = (1, 7, 14, 30)


@dataclass(frozen=True)
class RetailRocketCutoffs:
    train: datetime = datetime(2015, 7, 1, tzinfo=UTC)
    development_1: datetime = datetime(2015, 7, 15, tzinfo=UTC)
    development_2: datetime = datetime(2015, 7, 29, tzinfo=UTC)
    official_final: datetime = datetime(2015, 8, 19, tzinfo=UTC)


def load_events(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=["timestamp", "visitorid", "event", "itemid"])
    if not set(frame.event.unique()).issubset(EVENTS):
        raise ValueError("unexpected RetailRocket event mark")
    frame["event_time"] = pd.to_datetime(frame.timestamp, unit="ms", utc=True)
    return frame.sort_values(["visitorid", "event_time", "timestamp"], kind="stable")


def _history_features(history: pd.DataFrame, cutoff: datetime) -> pd.DataFrame:
    history = history.copy()
    history["interval_days"] = (
        history.groupby("visitorid", sort=False).event_time.diff().dt.total_seconds() / 86_400
    )
    grouped = history.groupby("visitorid", sort=False)
    result = grouped.agg(
        history_events=("event", "size"),
        first_event_time=("event_time", "min"),
        last_event_time=("event_time", "max"),
        unique_items=("itemid", "nunique"),
        mean_interval_days=("interval_days", "mean"),
        std_interval_days=("interval_days", "std"),
    )
    result["history_span_days"] = (
        result.last_event_time - result.first_event_time
    ).dt.total_seconds() / 86_400
    result["recency_days"] = (
        pd.Timestamp(cutoff) - result.last_event_time
    ).dt.total_seconds() / 86_400
    counts = pd.crosstab(history.visitorid, history.event).reindex(columns=EVENTS, fill_value=0)
    counts.columns = [f"{column}_count" for column in counts.columns]
    result = result.join(counts)
    last = grouped.tail(1).set_index("visitorid")["event"]
    for event in EVENTS:
        result[f"last_event_{event}"] = (last == event).astype(int)
        event_last = history[history.event == event].groupby("visitorid").event_time.max()
        result[f"{event}_recency_days"] = (
            pd.Timestamp(cutoff) - event_last
        ).dt.total_seconds() / 86_400
    duration = np.clip(result.history_span_days.to_numpy(float), 1.0, None)
    for event in EVENTS:
        result[f"{event}_rate_per_day"] = result[f"{event}_count"] / duration
    return result.reset_index()


def _future_targets(events: pd.DataFrame, cutoff: datetime, eligible: pd.Index) -> pd.DataFrame:
    target = pd.DataFrame({"visitorid": eligible})
    future_all = events[events.event_time >= cutoff]
    for horizon in HORIZONS:
        future = future_all[future_all.event_time < cutoff + timedelta(days=horizon)]
        counts = (
            future.groupby(["visitorid", "event"])
            .size()
            .unstack(fill_value=0)
            .reindex(eligible, fill_value=0)
        )
        for event in EVENTS:
            values = counts[event] if event in counts else pd.Series(0, index=eligible)
            target[f"{event}_count_{horizon}d"] = values.to_numpy(int)
            target[f"{event}_any_{horizon}d"] = (values.to_numpy(int) > 0).astype(int)
    first = future_all.groupby("visitorid", sort=False).first().reindex(eligible)
    target["next_event"] = (
        first.event.map({event: index for index, event in enumerate(EVENTS)})
        .fillna(-1)
        .to_numpy(int)
    )
    target["time_to_next_event_days"] = (
        (first.event_time - pd.Timestamp(cutoff)).dt.total_seconds().div(86_400).to_numpy(float)
    )
    target["next_event_observed"] = first.event.notna().to_numpy(int)
    return target


def snapshot(
    events: pd.DataFrame, cutoff: datetime, *, minimum_history: int = 3
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = events[events.event_time < cutoff]
    features = _history_features(history, cutoff)
    features = features[features.history_events >= minimum_history].copy()
    features["cutoff"] = pd.Timestamp(cutoff)
    features["first_event_time"] = features.first_event_time.astype("int64") // 1_000_000
    features["last_event_time"] = features.last_event_time.astype("int64") // 1_000_000
    numeric = features.select_dtypes(include=["number"]).columns
    features[numeric] = features[numeric].replace([np.inf, -np.inf], np.nan).fillna(0)
    targets = _future_targets(events, cutoff, pd.Index(features.visitorid))
    return features.reset_index(drop=True), targets.reset_index(drop=True)


def materialize_retailrocket(source: Path, output: Path) -> dict[str, int]:
    events = load_events(source)
    cutoffs = RetailRocketCutoffs()
    output.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, cutoff in (
        ("train", cutoffs.train),
        ("development_1", cutoffs.development_1),
        ("development_2", cutoffs.development_2),
        ("official_final", cutoffs.official_final),
    ):
        features, targets = snapshot(events, cutoff)
        features.to_parquet(output / f"{name}_features.parquet", index=False)
        targets.to_parquet(output / f"{name}_outcomes.parquet", index=False)
        counts[name] = len(features)
    return counts
