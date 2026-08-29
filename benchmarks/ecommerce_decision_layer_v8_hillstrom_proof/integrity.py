"""Fail-closed integrity controls for the V8 Hillstrom proof."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from decision_engine.economic_policy_v72.splits import stable_unit_hash

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
BASE_CHECKPOINT = "0a089ff1b1a73ba4cf6a1fd96c44a879f53aec3b"
RAW = REPOSITORY / "data/raw/hillstrom/hillstrom.csv"
DEVELOPMENT = REPOSITORY / "data/processed/hillstrom/v7_2/development.parquet"
MANIFEST = (
    REPOSITORY / "benchmarks/ecommerce_decision_layer_v7_2/manifests/hillstrom_split_manifest.json"
)
QUARANTINE = (
    REPOSITORY / "benchmarks/ecommerce_decision_layer_v7_2/HILLSTROM_SEALED_QUARANTINE.json"
)
BUY_BAITS_LOCK = (
    REPOSITORY / "benchmarks/ecommerce_decision_layer_v7_2/BUY_BAITS_DEVELOPMENT_LOCK.json"
)
RESULTS = ROOT / "results"
FREEZE_MANIFEST = ROOT / "V8_FREEZE_MANIFEST.json"
QA_RECORD = ROOT / "PRE_REVEAL_QA.json"
DEVELOPMENT_RESULT = RESULTS / "development_reconstruction.json"
REVEAL_START = RESULTS / "V8_REVEAL_STARTED.json"
VALIDATION_RESULT = ROOT / "V8_VALIDATION_RESULT.json"
CONSUMED_LOCK = RESULTS / "V8_VALIDATION_CONSUMED.json"

EXPECTED_RAW_SHA256 = "27bab8c5d3669f26ec08ebb50a0a78317542f29501156f2e2af6781fab4cd7e2"
EXPECTED_MANIFEST_SHA256 = "ee3b2050b532c65c323870f8d54ecb8240981f87936ed7ec2c8045960e1e1d0f"
EXPECTED_QUARANTINE_SHA256 = "1b91162c0ee1d7971d083a6cedbf498686bdc243ada3f63dcad5326fc2184d38"
EXPECTED_BUY_BAITS_LOCK_SHA256 = "0e55fef69dfb9aa740e78f3f423c6adf686a024c6e0564337890e5449f4a44a0"
EXPECTED_DEVELOPMENT_SHA256 = "0e46a162e8bd201e487de30c5020b74516fd7b39208fce869f15babfc5724f13"
EXPECTED_ROWS = {"DEVELOPMENT": 32233, "VALIDATION": 15928, "SEALED_TEST": 15839}
EXPECTED_ARMS = {
    "DEVELOPMENT": {"Mens E-Mail": 10655, "No E-Mail": 10856, "Womens E-Mail": 10722},
    "VALIDATION": {"Mens E-Mail": 5371, "No E-Mail": 5192, "Womens E-Mail": 5365},
    "SEALED_TEST": {"Mens E-Mail": 5281, "No E-Mail": 5258, "Womens E-Mail": 5300},
}
EXPECTED_VALIDATION_IDS_SHA256 = "fe9df1271862da012d7703b215294d29fe6266627eb1560f8853d1be3705d9aa"

FROZEN_SOURCE_NAMES = (
    "CLAIM_CONTRACT.json",
    "FROZEN_ANALYSIS_CONFIG.json",
    "PREREGISTRATION.md",
    "V8_PREREGISTRATION.md",
    "development_reconstruction.py",
    "estimators.py",
    "freeze.py",
    "integrity.py",
    "report.py",
    "validation_runner.py",
)


class IntegrityError(RuntimeError):
    """Raised when V8 must stop as INVALID."""


@dataclass(frozen=True)
class IntegrityReport:
    base_checkpoint_is_ancestor: bool
    buy_baits_unchanged: bool
    development_hash_matches: bool
    manifest_hash_matches: bool
    quarantine_hash_matches: bool
    raw_hash_matches: bool
    row_counts_match: bool
    row_zero_quarantined: bool
    sealed_fully_untouched: bool
    split_disjoint: bool
    validation_ids_hash_matches: bool
    validation_materialization_absent: bool
    validation_result_absent: bool

    @property
    def passed(self) -> bool:
        values = asdict(self)
        required = {key: value for key, value in values.items() if key != "sealed_fully_untouched"}
        return all(required.values()) and not self.sealed_fully_untouched

    def as_dict(self) -> dict[str, bool]:
        return {**asdict(self), "passed": self.passed}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_id_manifest(values: list[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPOSITORY, text=True, stderr=subprocess.STDOUT
    ).strip()


def current_head() -> str:
    return git("rev-parse", "HEAD")


def source_hashes() -> dict[str, str]:
    return {name: sha256_file(ROOT / name) for name in FROZEN_SOURCE_NAMES}


def source_tree_hash(hashes: dict[str, str] | None = None) -> str:
    values = hashes or source_hashes()
    return canonical_json_hash(values)


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text())


def validation_has_been_consumed() -> bool:
    return REVEAL_START.exists() or VALIDATION_RESULT.exists() or CONSUMED_LOCK.exists()


def audit_pre_reveal() -> IntegrityReport:
    manifest = load_manifest()
    unit_hashes = {key: set(values) for key, values in manifest["unit_hashes"].items()}
    row_zero = stable_unit_hash("hillstrom", "row-0")
    quarantine = json.loads(QUARANTINE.read_text())
    processed_validation = list((REPOSITORY / "data/processed/hillstrom").glob("**/validation*"))
    validation_artifacts = validation_has_been_consumed()
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASE_CHECKPOINT, "HEAD"],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
        )
        base_is_ancestor = True
    except subprocess.CalledProcessError:
        base_is_ancestor = False
    split_disjoint = (
        not (unit_hashes["DEVELOPMENT"] & unit_hashes["VALIDATION"])
        and not (unit_hashes["DEVELOPMENT"] & unit_hashes["SEALED_TEST"])
        and not (unit_hashes["VALIDATION"] & unit_hashes["SEALED_TEST"])
    )
    return IntegrityReport(
        base_checkpoint_is_ancestor=base_is_ancestor,
        buy_baits_unchanged=sha256_file(BUY_BAITS_LOCK) == EXPECTED_BUY_BAITS_LOCK_SHA256,
        development_hash_matches=sha256_file(DEVELOPMENT) == EXPECTED_DEVELOPMENT_SHA256,
        manifest_hash_matches=sha256_file(MANIFEST) == EXPECTED_MANIFEST_SHA256,
        quarantine_hash_matches=sha256_file(QUARANTINE) == EXPECTED_QUARANTINE_SHA256,
        raw_hash_matches=sha256_file(RAW) == EXPECTED_RAW_SHA256,
        row_counts_match=manifest["row_counts"] == EXPECTED_ROWS
        and manifest["treatment_counts"] == EXPECTED_ARMS,
        row_zero_quarantined=(
            row_zero in unit_hashes["SEALED_TEST"]
            and row_zero not in unit_hashes["DEVELOPMENT"]
            and row_zero not in unit_hashes["VALIDATION"]
            and quarantine["affected_unit_hash"] == row_zero
            and quarantine["status"] == "QUARANTINED_INTEGRITY_INCIDENT"
        ),
        sealed_fully_untouched=bool(quarantine["sealed_test_fully_untouched"]),
        split_disjoint=split_disjoint,
        validation_ids_hash_matches=(
            hash_id_manifest(manifest["unit_hashes"]["VALIDATION"])
            == EXPECTED_VALIDATION_IDS_SHA256
        ),
        validation_materialization_absent=not processed_validation,
        validation_result_absent=not validation_artifacts,
    )


def require_pre_reveal_integrity() -> IntegrityReport:
    report = audit_pre_reveal()
    if not report.passed:
        raise IntegrityError(f"V8 pre-reveal integrity failed: {report.as_dict()}")
    return report


def verify_frozen_sources(freeze: dict[str, Any]) -> None:
    observed = source_hashes()
    if observed != freeze["frozen_source_files"]:
        raise IntegrityError("frozen V8 source/config mutation detected")
    if source_tree_hash(observed) != freeze["source_tree_sha256"]:
        raise IntegrityError("frozen V8 source-tree hash mismatch")
    if sha256_file(MANIFEST) != freeze["split_manifest_sha256"]:
        raise IntegrityError("Hillstrom split manifest mutation detected")
    if sha256_file(QUARANTINE) != freeze["quarantine_record_sha256"]:
        raise IntegrityError("Hillstrom quarantine record mutation detected")
    if not QA_RECORD.exists() or sha256_file(QA_RECORD) != freeze["pre_reveal_qa_sha256"]:
        raise IntegrityError("pre-reveal QA record missing or mutated")
    qa = json.loads(QA_RECORD.read_text())
    if not qa.get("all_required_checks_passed", False):
        raise IntegrityError("pre-reveal QA did not pass")


def v8_worktree_is_clean() -> bool:
    output = git("status", "--porcelain", "--", str(ROOT.relative_to(REPOSITORY)))
    return not output
