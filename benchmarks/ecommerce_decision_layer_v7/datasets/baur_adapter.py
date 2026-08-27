"""Contract-only BAUR adapter; row data is intentionally not acquired or fabricated."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BaurAcquisitionStatus:
    available: bool = False
    lawful_public_url: str | None = None
    reason: str = (
        "The publication was located, but no lawful public row-level dataset was verified. "
        "Contact the authors or publisher; do not scrape or synthesize purported BAUR rows."
    )


def load_baur_profit_uplift() -> None:
    raise FileNotFoundError(BaurAcquisitionStatus().reason)

