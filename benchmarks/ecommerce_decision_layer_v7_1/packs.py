"""Deterministic disjoint V7.1 pack specifications and sealed final commitment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

import numpy as np

from .world import V71WorldFamily, V71WorldSpec

PACK_ROOTS = {
    "O": 111_000,
    "P": 112_000,
    "Q": 113_000,
    "R": 121_000,
    "S": 122_000,
    "T": 123_000,
    "U": 131_000,
}


def v71_pack_specs(pack: str) -> tuple[V71WorldSpec, ...]:
    if pack not in PACK_ROOTS:
        raise ValueError(f"unknown V7.1 pack: {pack}")
    root = PACK_ROOTS[pack]
    rng = np.random.default_rng(root)
    specs: list[V71WorldSpec] = []
    noise_options = ("gaussian", "student_t", "zero_inflated")
    for index, family in enumerate(V71WorldFamily):
        specs.append(
            V71WorldSpec(
                world_id=f"{pack}-{index:02d}-{family.value.lower()}",
                merchant_id=f"v71-merchant-{pack}-{index:02d}",
                action_family=f"v71-family-{(index + ord(pack)) % 7}",
                family=family,
                seed=root + 137 * index + 17,
                observations=3_000,
                periods=10,
                treatment_cost=float(rng.uniform(0.18, 0.32)),
                switching_cost=float(rng.uniform(0.02, 0.06)),
                subgroup_prevalence=float(rng.uniform(0.025, 0.045))
                if family is V71WorldFamily.NONMATERIAL_SPARSE
                else float(rng.uniform(0.18, 0.30)),
                maturity_delay=int(rng.integers(1, 5)),
                change_period=int(rng.integers(3, 7)),
                noise_family=noise_options[(index + ord(pack)) % len(noise_options)],
            )
        )
    return tuple(specs)


def pack_payload(pack: str) -> dict[str, object]:
    specs = [asdict(spec) for spec in v71_pack_specs(pack)]
    canonical = json.dumps(specs, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "schema_version": 1,
        "pack": pack,
        "role": "DEVELOPMENT" if pack in "OPQ" else "VALIDATION" if pack in "RST" else "FINAL",
        "worlds": specs,
        "spec_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "legacy_v6_inputs": False,
        "oracle_available_to_policy": False,
    }


def write_pack_manifest(pack: str, directory: Path) -> Path:
    if pack == "U":
        raise PermissionError("Pack U is sealed and cannot be materialized by this command")
    path = directory / f"pack_{pack}_manifest.json"
    encoded = json.dumps(pack_payload(pack), indent=2, sort_keys=True, default=str) + "\n"
    if path.exists() and path.read_text() != encoded:
        raise RuntimeError(f"immutable pack manifest changed: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded)
    return path


def final_commitment() -> dict[str, object]:
    payload = pack_payload("U")
    worlds = cast(list[object], payload["worlds"])
    return {
        "pack": "U",
        "status": "SEALED_NOT_MATERIALIZED",
        "commitment_sha256": payload["spec_sha256"],
        "world_count": len(worlds),
    }
