from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
RAW_ROOT = WORKSPACE / "data" / "raw" / "mt_lift"
QUALIFICATION_RESULT = ROOT / "V10_QUALIFICATION_RESULT.json"
SOURCE_MANIFEST = ROOT / "manifests" / "V10_SOURCE_MANIFEST.json"

V8_RESULT_COMMIT = "0fa794497dcea419a9322b70e5f69291a41d3c2c"
V9_RESULT_COMMIT = "e4fefa96c0334971413fa3b73104158585edb5fb"
V8_PATH = "benchmarks/ecommerce_decision_layer_v8_hillstrom_proof"
V9_PATH = "benchmarks/ecommerce_decision_layer_v9_concealing_prices"

EXPECTED_REFERENCE_SHA256 = {
    "references/2402.03379.pdf": (
        "36e0024ebc976c53ab33ac058963581545b13d489cc3ec0ba9d28453fca4abe7"
    ),
    "references/README-379b315.md": (
        "1598c913bb2e715c384141ad716794d2c827356b492213bb864369419d5f8ca6"
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_reference_hashes() -> dict[str, str]:
    observed = {
        relative: sha256(RAW_ROOT / relative) for relative in EXPECTED_REFERENCE_SHA256
    }
    if observed != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError("V10 official reference hash mismatch")
    return observed


def verify_no_dataset_payload() -> None:
    prohibited = (RAW_ROOT / "train.csv", RAW_ROOT / "test.csv")
    if any(path.exists() for path in prohibited):
        raise RuntimeError("Unexpected MT-LIFT outcome-bearing payload exists")


def verify_outcome_isolation() -> dict[str, Any]:
    result = load_json(QUALIFICATION_RESULT)
    access = result["access_control"]
    if any(
        access[key]
        for key in (
            "development_outcomes_opened",
            "test_outcomes_opened",
            "model_selection_performed",
            "freeze_created",
            "reveal_started",
        )
    ):
        raise RuntimeError("V10 qualification is not outcome-isolated")
    verify_no_dataset_payload()
    return result

def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )


def verify_immutable_history() -> None:
    for commit in (V8_RESULT_COMMIT, V9_RESULT_COMMIT):
        result = _git("merge-base", "--is-ancestor", commit, "HEAD")
        if result.returncode != 0:
            raise RuntimeError(f"Required immutable commit is not an ancestor: {commit}")
    for commit, path in ((V8_RESULT_COMMIT, V8_PATH), (V9_RESULT_COMMIT, V9_PATH)):
        result = _git("diff", "--quiet", commit, "HEAD", "--", path)
        if result.returncode != 0:
            raise RuntimeError(f"Immutable benchmark path changed after {commit}: {path}")


def verify_qualification_checkpoint() -> dict[str, Any]:
    verify_reference_hashes()
    verify_immutable_history()
    result = verify_outcome_isolation()
    if result["final_status"] != "V10_DATASET_NOT_CAUSALLY_QUALIFIED":
        raise RuntimeError("Unexpected V10 qualification status")
    if result["qualified_for_causal_personalization"]:
        raise RuntimeError("Inaccessible MT-LIFT release cannot be marked qualified")
    return result
