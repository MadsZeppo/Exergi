"""Leak-safe JDsearch behavioral snapshot construction.

JDsearch publishes ordered per-user histories and inter-event intervals, but no
documented interval unit or shared absolute timestamp.  This module therefore uses
an event-count horizon and never calls it a calendar-day forecast.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

EVENT_TYPES = ("ORD", "CLICK", "CART", "FLW")
WINDOWS = (1, 3, 5, 10, 20)
SNAPSHOT_REMAINING = (40, 35, 30, 25, 20, 15, 10, 5)
HORIZON_EVENTS = 5


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_list(value: str) -> list[str]:
    return [] if not value else value.split("_")


def event_times(intervals: Iterable[str], event_count: int) -> np.ndarray:
    """Reconstruct a within-user monotonic clock; its physical unit is unknown."""
    values = np.asarray([float(item) for item in intervals], float)
    if np.any(values < 0):
        raise ValueError("history intervals must be nonnegative")
    if len(values) != event_count + 1:
        raise ValueError("history_time_list must contain one more value than history events")
    return np.cumsum(values[:-1])


def validate_row(
    types: list[str], products: list[str], queries: list[str], times: list[str]
) -> None:
    if not (len(types) == len(products) == len(queries)):
        raise ValueError("history type/product/query lists must be aligned")
    if len(times) != len(types) + 1:
        raise ValueError("history time list must include history events plus test query")
    if any(item not in EVENT_TYPES for item in types):
        raise ValueError("unknown interaction type")


def _recency(types: np.ndarray, kind: str, cutoff: int) -> float:
    selected = np.flatnonzero(types[:cutoff] == kind)
    return float(cutoff - 1 - selected[-1]) if len(selected) else float(cutoff + 1)


def _transition_count(
    types: np.ndarray, left: str, right: str, cutoff: int, window: int | None
) -> int:
    start = 0 if window is None else max(0, cutoff - window)
    sequence = types[start:cutoff]
    if len(sequence) < 2:
        return 0
    return int(np.sum((sequence[:-1] == left) & (sequence[1:] == right)))


def build_snapshot(
    *,
    user_key: int,
    snapshot_index: int,
    cutoff: int,
    types: list[str],
    products: list[str],
    queries: list[str],
    times: list[str],
) -> dict[str, float | int | str]:
    """Build features strictly from ``[:cutoff]`` and label from the next five events."""
    type_array = np.asarray(types, object)
    product_array = np.asarray(products, object)
    query_array = np.asarray(queries, object)
    clock = event_times(times, len(types))
    history_types = type_array[:cutoff]
    future_types = type_array[cutoff : cutoff + HORIZON_EVENTS]
    row: dict[str, float | int | str] = {
        "user_key": user_key,
        "snapshot_index": snapshot_index,
        "cutoff_event": cutoff,
        "history_events": cutoff,
        "label_future_purchase": int(np.any(future_types == "ORD")),
        "future_start_event": cutoff,
        "future_end_event": cutoff + HORIZON_EVENTS,
        "elapsed_interval_units": float(clock[cutoff - 1] - clock[0]) if cutoff > 1 else 0.0,
        "mean_interval": float(np.mean(np.diff(clock[:cutoff]))) if cutoff > 1 else 0.0,
        "std_interval": float(np.std(np.diff(clock[:cutoff]))) if cutoff > 2 else 0.0,
        "unique_products_all": int(len(set(product_array[:cutoff]))),
        "query_linked_all": int(np.sum(query_array[:cutoff] != "-1")),
        "unique_queries_all": int(len(set(query_array[:cutoff]) - {"-1"})),
    }
    for kind in EVENT_TYPES:
        lower = kind.lower()
        row[f"{lower}_count_all"] = int(np.sum(history_types == kind))
        row[f"{lower}_recency_events"] = _recency(type_array, kind, cutoff)
        row[f"{lower}_unique_products"] = int(
            len(set(product_array[:cutoff][history_types == kind]))
        )
        for window in WINDOWS:
            row[f"{lower}_count_{window}"] = int(
                np.sum(type_array[max(0, cutoff - window) : cutoff] == kind)
            )
    for window in WINDOWS:
        recent_queries = query_array[max(0, cutoff - window) : cutoff]
        row[f"query_linked_{window}"] = int(np.sum(recent_queries != "-1"))
    row["click_to_ord_ratio"] = (float(row["ord_count_all"]) + 1) / (
        float(row["click_count_all"]) + 2
    )
    row["cart_to_ord_ratio"] = (float(row["ord_count_all"]) + 1) / (
        float(row["cart_count_all"]) + 2
    )
    row["query_to_ord_ratio"] = (float(row["ord_count_all"]) + 1) / (
        float(row["query_linked_all"]) + 2
    )
    row["recent_intent_acceleration"] = (
        float(row["click_count_5"]) + 2 * float(row["cart_count_5"])
    ) / max((float(row["click_count_all"]) + 2 * float(row["cart_count_all"])) / cutoff * 5, 1)
    for left, right in (("CLICK", "CART"), ("CART", "ORD"), ("CLICK", "ORD")):
        name = f"transition_{left.lower()}_{right.lower()}"
        row[f"{name}_all"] = _transition_count(type_array, left, right, cutoff, None)
        row[f"{name}_10"] = _transition_count(type_array, left, right, cutoff, 10)
    return row


@dataclass(frozen=True)
class SnapshotAudit:
    source_rows: int
    eligible_users: int
    snapshots: int
    malformed_rows: int
    event_counts: dict[str, int]


def materialize_snapshots(source: Path, target: Path) -> SnapshotAudit:
    rows: list[dict[str, float | int | str]] = []
    source_rows = eligible = malformed = 0
    event_counts = {kind: 0 for kind in EVENT_TYPES}
    with source.open("r", encoding="utf-8", errors="strict") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        if header != [
            "query",
            "candidate_wid_list",
            "candidate_label_list",
            "history_qry_list",
            "history_wid_list",
            "history_type_list",
            "history_time_list",
        ]:
            raise ValueError("unexpected JDsearch user file schema")
        for user_key, line in enumerate(handle):
            source_rows += 1
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 7:
                malformed += 1
                continue
            queries, products, types, times = map(parse_list, fields[3:7])
            try:
                validate_row(types, products, queries, times)
            except ValueError:
                malformed += 1
                continue
            for kind in EVENT_TYPES:
                event_counts[kind] += types.count(kind)
            if len(types) < max(SNAPSHOT_REMAINING) + HORIZON_EVENTS:
                continue
            eligible += 1
            for snapshot_index, remaining in enumerate(SNAPSHOT_REMAINING):
                cutoff = len(types) - remaining
                rows.append(
                    build_snapshot(
                        user_key=user_key,
                        snapshot_index=snapshot_index,
                        cutoff=cutoff,
                        types=types,
                        products=products,
                        queries=queries,
                        times=times,
                    )
                )
    frame = pd.DataFrame(rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target, index=False)
    return SnapshotAudit(source_rows, eligible, len(frame), malformed, event_counts)


PURCHASE_ONLY_FEATURES = tuple(
    column
    for column in (
        "history_events",
        "elapsed_interval_units",
        "mean_interval",
        "std_interval",
        "ord_count_all",
        "ord_recency_events",
        "ord_unique_products",
        *(f"ord_count_{window}" for window in WINDOWS),
    )
)

BEHAVIORAL_FEATURES = tuple(
    column
    for column in (
        *PURCHASE_ONLY_FEATURES,
        "unique_products_all",
        "query_linked_all",
        "unique_queries_all",
        *(f"query_linked_{window}" for window in WINDOWS),
        *(f"{kind.lower()}_count_all" for kind in ("CLICK", "CART", "FLW")),
        *(f"{kind.lower()}_recency_events" for kind in ("CLICK", "CART", "FLW")),
        *(f"{kind.lower()}_unique_products" for kind in ("CLICK", "CART", "FLW")),
        *(
            f"{kind.lower()}_count_{window}"
            for kind in ("CLICK", "CART", "FLW")
            for window in WINDOWS
        ),
        "click_to_ord_ratio",
        "cart_to_ord_ratio",
        "query_to_ord_ratio",
        "recent_intent_acceleration",
        "transition_click_cart_all",
        "transition_click_cart_10",
        "transition_cart_ord_all",
        "transition_cart_ord_10",
        "transition_click_ord_all",
        "transition_click_ord_10",
    )
)


def assert_purchase_only_is_clean(features: Iterable[str]) -> None:
    forbidden = ("click", "cart", "flw", "query", "intent", "transition")
    if any(any(token in feature for token in forbidden) for feature in features):
        raise AssertionError("purchase-only schema contains behavioral intent")


def support_groups(frame: pd.DataFrame) -> np.ndarray:
    purchases = frame["ord_count_all"].to_numpy()
    behavior = frame["history_events"].to_numpy()
    return np.select(
        [
            (purchases <= 1) & (behavior < 20),
            (purchases <= 1) & (behavior >= 20),
            (purchases >= 5) & (behavior >= 20),
        ],
        [
            "PURCHASE_SPARSE_BEHAVIOR_SPARSE",
            "PURCHASE_SPARSE_BEHAVIOR_RICH",
            "PURCHASE_RICH_BEHAVIOR_RICH",
        ],
        default="MIXED",
    )
