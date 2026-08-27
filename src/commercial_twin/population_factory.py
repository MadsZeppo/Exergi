from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import polars as pl

from commercial_twin.population_contracts import (
    CustomerPopulationSnapshot,
    CustomerTwinReadinessReport,
    PopulationComparison,
)
from commercial_twin.population_ingestion import Rees46EventAdapter
from commercial_twin.population_state import (
    attach_affinities,
    build_cohorts,
    build_customer_states,
    build_population_snapshot,
    compare_population,
)

REQUIRED_EVENT_COLUMNS = {
    "event_time",
    "customer_id",
    "event_type",
    "product_id",
    "category_id",
    "price",
}


@dataclass
class CustomerPopulationEngine:
    events: pl.DataFrame
    seed: int = 42
    n_cohorts: int = 8

    def build_population(self, as_of: datetime) -> CustomerPopulationSnapshot:
        states = attach_affinities(self.events, build_customer_states(self.events, as_of), as_of)
        labeled, cohorts = build_cohorts(states, n_cohorts=self.n_cohorts, seed=self.seed)
        return build_population_snapshot(labeled, cohorts, as_of=as_of)

    def update_population(
        self, new_events: pl.DataFrame, *, as_of: datetime | None = None
    ) -> CustomerPopulationSnapshot:
        CustomerTwinFactory.validate_events(new_events)
        self.events = pl.concat([self.events, new_events], how="diagonal_relaxed").unique(
            maintain_order=True
        )
        resolved = as_of or self.events["event_time"].max()
        if not isinstance(resolved, datetime):
            raise ValueError("event_time must contain datetimes")
        return self.build_population(resolved)

    @staticmethod
    def compare_population(
        earlier: CustomerPopulationSnapshot, later: CustomerPopulationSnapshot
    ) -> PopulationComparison:
        return compare_population(earlier, later)


@dataclass(frozen=True)
class CustomerTwinBuildResult:
    engine: CustomerPopulationEngine
    snapshot: CustomerPopulationSnapshot
    readiness: CustomerTwinReadinessReport


class CustomerTwinFactory:
    @staticmethod
    def validate_events(events: pl.DataFrame) -> None:
        missing = REQUIRED_EVENT_COLUMNS - set(events.columns)
        if missing:
            raise ValueError(f"canonical customer events missing: {sorted(missing)}")
        if events.is_empty():
            raise ValueError("customer events cannot be empty")
        if events["customer_id"].null_count() or events["event_time"].null_count():
            raise ValueError("customer_id and event_time cannot be null")

    @staticmethod
    def _readiness(events: pl.DataFrame) -> CustomerTwinReadinessReport:
        start = events["event_time"].min()
        end = events["event_time"].max()
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise ValueError("event_time must contain datetimes")
        customer_counts = events.group_by("customer_id").len()
        event_counts = events.group_by("event_type").len()
        purchases = events.filter(pl.col("event_type") == "purchase")
        reasons: list[str] = []
        if (end - start).days < 120:
            reasons.append("less than 120 days of behavioral history")
        return CustomerTwinReadinessReport(
            history_days=(end - start).days,
            active_customers=events["customer_id"].n_unique(),
            repeat_customers=customer_counts.filter(pl.col("len") > 1).height,
            event_coverage={
                str(row["event_type"]): int(row["len"])
                for row in event_counts.iter_rows(named=True)
            },
            transaction_coverage=purchases.height / events.height,
            category_coverage=1 - events["category_id"].null_count() / events.height,
            sparsity=float(cast(float, (customer_counts["len"] <= 2).mean())),
            reasons=tuple(reasons),
        )

    @classmethod
    def from_events(
        cls,
        events: pl.DataFrame,
        *,
        as_of: datetime | None = None,
        seed: int = 42,
        n_cohorts: int = 8,
    ) -> CustomerTwinBuildResult:
        cls.validate_events(events)
        ordered = events.sort("event_time")
        resolved = as_of or ordered["event_time"].max()
        if not isinstance(resolved, datetime):
            raise ValueError("event_time must contain datetimes")
        engine = CustomerPopulationEngine(ordered, seed=seed, n_cohorts=n_cohorts)
        return CustomerTwinBuildResult(
            engine=engine,
            snapshot=engine.build_population(resolved),
            readiness=cls._readiness(ordered),
        )

    @classmethod
    def from_canonical_files(
        cls,
        paths: tuple[Path, ...],
        *,
        source_format: str = "canonical",
        as_of: datetime | None = None,
        seed: int = 42,
    ) -> CustomerTwinBuildResult:
        frames: list[pl.DataFrame] = []
        for path in paths:
            if source_format == "rees46":
                frames.append(Rees46EventAdapter.read(path))
            elif path.suffix == ".parquet":
                frames.append(pl.read_parquet(path))
            else:
                frames.append(pl.read_csv(path, try_parse_dates=True))
        return cls.from_events(pl.concat(frames, how="diagonal_relaxed"), as_of=as_of, seed=seed)
