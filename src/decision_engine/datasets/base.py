"""Canonical dataset boundary; adapters preserve source columns alongside canonical ones."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import polars as pl

REQUIRED_COLUMNS = {
    "timestamp",
    "entity_id",
    "group_id",
    "action",
    "outcome",
    "observed_at",
    "effective_at",
}


@dataclass(frozen=True)
class DatasetMetadata:
    name: str
    version: str
    randomized: bool = False
    known_propensity: bool = False


class DecisionDataset(ABC):
    metadata: DatasetMetadata

    @abstractmethod
    def load(self) -> pl.DataFrame:
        """Return canonical rows and retain useful original source fields."""

    def validate(self, frame: pl.DataFrame) -> None:
        missing = REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"canonical dataset missing columns: {sorted(missing)}")
        if frame.filter(pl.col("observed_at") > pl.col("effective_at")).height:
            raise ValueError("observed_at after effective_at requires explicit adapter handling")
