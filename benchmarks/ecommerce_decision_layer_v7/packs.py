"""Disjoint V7 pack definitions and immutable manifest writer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .world import WorldFamily, WorldSpec

PACK_SEEDS = {
    "H": 71_000,
    "I": 72_000,
    "J": 73_000,
    "K": 81_000,
    "L": 82_000,
    "M": 83_000,
    "N": 91_000,
}


def pack_specs(pack: str) -> tuple[WorldSpec, ...]:
    if pack not in PACK_SEEDS:
        raise ValueError(f"unknown pack: {pack}")
    root = PACK_SEEDS[pack]
    return tuple(
        WorldSpec(
            world_id=f"{pack}-{index:02d}-{family.value.lower()}",
            merchant_id=f"merchant-{pack}-{index:02d}",
            action_family=f"family-{(index + ord(pack)) % 5}",
            family=family,
            seed=root + 101 * index,
        )
        for index, family in enumerate(WorldFamily)
    )


def manifest_payload(pack: str) -> dict[str, object]:
    specs = [asdict(spec) for spec in pack_specs(pack)]
    canonical = json.dumps(specs, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "schema_version": 1,
        "pack": pack,
        "role": "DEVELOPMENT" if pack in "HIJ" else "VALIDATION" if pack in "KLM" else "FINAL",
        "worlds": specs,
        "spec_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "oracle_in_policy_inputs": False,
    }


def write_manifest(pack: str, directory: Path) -> Path:
    if pack == "N":
        raise PermissionError(
            "Final Pack N can only be materialized by the one-time reveal command"
        )
    path = directory / f"pack_{pack}_manifest.json"
    payload = json.dumps(manifest_payload(pack), indent=2, sort_keys=True, default=str) + "\n"
    if path.exists() and path.read_text() != payload:
        raise RuntimeError(f"frozen manifest changed: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
    return path
