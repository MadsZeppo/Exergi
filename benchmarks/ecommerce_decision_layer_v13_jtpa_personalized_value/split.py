from __future__ import annotations

import hashlib
import json
from typing import Literal

from .qualification import OUTCOME_SCHEMA, ROOT, _normalized_ids

SPLIT_SALT = "EXERGI_V13_JTPA_60_40_V1"
DEVELOPMENT_SHARE = 0.60
SPLIT_MANIFEST = ROOT / "manifests" / "V13_SPLIT_MANIFEST.json"


def official_analysis_ids() -> set[str]:
    regular = set(_normalized_ids(OUTCOME_SCHEMA / "earns2.dta"))
    arrestee = set(_normalized_ids(OUTCOME_SCHEMA / "boysern2.dta"))
    scaled_ui = set(_normalized_ids(OUTCOME_SCHEMA / "analysis" / "scaledui.dta"))
    return (regular | arrestee) & scaled_ui


def assignment_for(recid: str) -> Literal["DEVELOPMENT", "VALIDATION"]:
    digest = hashlib.sha256(f"{SPLIT_SALT}:{recid}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    return "DEVELOPMENT" if value < DEVELOPMENT_SHARE else "VALIDATION"


def split_ids() -> tuple[set[str], set[str]]:
    development: set[str] = set()
    validation: set[str] = set()
    for recid in official_analysis_ids():
        target = development if assignment_for(recid) == "DEVELOPMENT" else validation
        target.add(recid)
    return development, validation


def hash_lines(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def build_manifest() -> dict[str, object]:
    development, validation = split_ids()
    labelled = [f"{recid}:{assignment_for(recid)}" for recid in sorted(development | validation)]
    return {
        "development_count": len(development),
        "development_id_hash": hash_lines(sorted(development)),
        "development_share_rule": DEVELOPMENT_SHARE,
        "hash_algorithm": "SHA256_FIRST_64_BITS_UNIFORM",
        "participant_count": len(development | validation),
        "schema_version": 1,
        "source_qualification_commit": "47f46a3594493dd8febc614d011d9bda0564d64c",
        "split_hash": hash_lines(labelled),
        "split_salt": SPLIT_SALT,
        "validation_count": len(validation),
        "validation_id_hash": hash_lines(sorted(validation)),
        "validation_outcomes_opened": False,
    }


def main() -> None:
    SPLIT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_MANIFEST.write_text(
        json.dumps(build_manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
