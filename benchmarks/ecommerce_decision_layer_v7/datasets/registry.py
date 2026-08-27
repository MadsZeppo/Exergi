"""Strict reader for the immutable V7 dataset evidence registry."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from decision_engine.core.authority import ClaimAuthority


@dataclass(frozen=True)
class DatasetEvidence:
    name: str
    source_url: str
    local_path: str | None
    sha256: str | None
    assignment_provenance: str
    known_propensity: bool
    cost_availability: str
    claim_authority: ClaimAuthority
    allowed_claims: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    raw: dict[str, Any]

    def verify_file(self, repository_root: Path) -> bool | None:
        if self.local_path is None or self.sha256 is None:
            return None
        path = repository_root / self.local_path
        if not path.is_file():
            return False
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest == self.sha256


class DatasetRegistry:
    def __init__(self, entries: dict[str, DatasetEvidence]) -> None:
        self._entries = dict(entries)

    @classmethod
    def load(cls, path: Path) -> DatasetRegistry:
        document = yaml.safe_load(path.read_text())
        if document.get("schema_version") != 1:
            raise ValueError("unsupported registry schema")
        entries: dict[str, DatasetEvidence] = {}
        for name, raw in document["datasets"].items():
            required = {
                "source_url",
                "assignment_provenance",
                "known_propensity",
                "cost_availability",
                "claim_authority",
                "allowed_claims",
                "forbidden_claims",
            }
            missing = required.difference(raw)
            if missing:
                raise ValueError(f"{name} is missing registry fields: {sorted(missing)}")
            entries[name] = DatasetEvidence(
                name=name,
                source_url=str(raw["source_url"]),
                local_path=raw.get("local_path"),
                sha256=raw.get("sha256"),
                assignment_provenance=str(raw["assignment_provenance"]),
                known_propensity=bool(raw["known_propensity"]),
                cost_availability=str(raw["cost_availability"]),
                claim_authority=ClaimAuthority(raw["claim_authority"]),
                allowed_claims=tuple(raw["allowed_claims"]),
                forbidden_claims=tuple(raw["forbidden_claims"]),
                raw=dict(raw),
            )
        return cls(entries)

    def get(self, name: str) -> DatasetEvidence:
        return self._entries[name]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

