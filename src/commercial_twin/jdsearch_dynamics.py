"""Event-time state/target materialization for the JDsearch dynamics benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from commercial_twin.dynamic_customer_state import stable_customer_split
from commercial_twin.jdsearch_behavioral import (
    EVENT_TYPES,
    build_snapshot,
    parse_list,
    validate_row,
)

EVENT_TO_INDEX = {name: index for index, name in enumerate(EVENT_TYPES)}
HORIZONS = (5, 10, 20)
SEQUENCE_LENGTH = 20


def snapshot_positions(event_count: int, *, split: str) -> list[int]:
    """Choose bounded chronological positions with exactly 20 future events available."""
    if event_count < 40:
        return []
    latest = event_count - max(HORIZONS)
    if split == "TRAIN":
        positions = list(range(max(SEQUENCE_LENGTH, latest - 80), latest + 1, 20))
        return positions[-5:]
    if split == "DEVELOPMENT":
        return sorted(set([max(SEQUENCE_LENGTH, latest - 20), latest]))
    return [latest]


def dynamics_row(
    *,
    customer_key: int,
    position_index: int,
    cutoff: int,
    types: list[str],
    products: list[str],
    queries: list[str],
    times: list[str],
) -> tuple[dict[str, float | int | str], dict[str, float | int]]:
    base = build_snapshot(
        user_key=customer_key,
        snapshot_index=position_index,
        cutoff=cutoff,
        types=types,
        products=products,
        queries=queries,
        times=times,
    )
    base.pop("label_future_purchase")
    base.pop("future_start_event")
    base.pop("future_end_event")
    base["split"] = stable_customer_split(customer_key)
    sequence_types = types[max(0, cutoff - SEQUENCE_LENGTH) : cutoff]
    sequence_times = [float(item) for item in times[max(0, cutoff - SEQUENCE_LENGTH) : cutoff]]
    pad = SEQUENCE_LENGTH - len(sequence_types)
    sequence_types = ["PAD"] * pad + sequence_types
    sequence_times = [0.0] * pad + sequence_times
    for index, (event, interval) in enumerate(zip(sequence_types, sequence_times, strict=True)):
        base[f"sequence_type_{index}"] = EVENT_TO_INDEX.get(event, -1)
        base[f"sequence_interval_{index}"] = float(np.log1p(max(interval, 0)))
    target: dict[str, float | int] = {
        "customer_key": customer_key,
        "position_index": position_index,
        "as_of_event": cutoff,
        "next_event": EVENT_TO_INDEX[types[cutoff]],
    }
    for horizon in HORIZONS:
        future = np.asarray(types[cutoff : cutoff + horizon], object)
        for event in EVENT_TYPES:
            count = int(np.sum(future == event))
            target[f"{event.lower()}_any_{horizon}"] = int(count > 0)
            target[f"{event.lower()}_count_{horizon}"] = count
            target[f"{event.lower()}_share_{horizon}"] = count / horizon
    return base, target


@dataclass(frozen=True)
class DynamicsAudit:
    eligible_customers: dict[str, int]
    snapshots: dict[str, int]
    target_prevalence: dict[str, dict[str, float]]


def materialize_dynamics(source: Path, directory: Path) -> DynamicsAudit:
    feature_rows: dict[str, list[dict[str, float | int | str]]] = {
        name: [] for name in ("TRAIN", "DEVELOPMENT", "OFFICIAL_FINAL")
    }
    target_rows: dict[str, list[dict[str, float | int]]] = {name: [] for name in feature_rows}
    eligible = {name: 0 for name in feature_rows}
    with source.open("r", encoding="utf-8") as handle:
        handle.readline()
        for customer_key, line in enumerate(handle):
            fields = line.rstrip("\n").split("\t")
            queries, products, types, times = map(parse_list, fields[3:7])
            validate_row(types, products, queries, times)
            split = stable_customer_split(customer_key)
            positions = snapshot_positions(len(types), split=split)
            if positions:
                eligible[split] += 1
            for position_index, cutoff in enumerate(positions):
                features, targets = dynamics_row(
                    customer_key=customer_key,
                    position_index=position_index,
                    cutoff=cutoff,
                    types=types,
                    products=products,
                    queries=queries,
                    times=times,
                )
                feature_rows[split].append(features)
                target_rows[split].append(targets)
    directory.mkdir(parents=True, exist_ok=True)
    prevalence: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}
    for split in feature_rows:
        features = pd.DataFrame(feature_rows[split])
        targets = pd.DataFrame(target_rows[split])
        features.to_parquet(directory / f"{split.lower()}_features.parquet", index=False)
        targets.to_parquet(directory / f"{split.lower()}_targets.parquet", index=False)
        counts[split] = len(features)
        prevalence[split] = {
            column: float(targets[column].mean())
            for column in targets.columns
            if column.startswith(("ord_any", "cart_any", "click_any"))
        }
    return DynamicsAudit(eligible, counts, prevalence)
