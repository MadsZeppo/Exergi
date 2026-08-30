from __future__ import annotations

import csv
import hashlib
import json
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
RAW_ROOT = WORKSPACE / "data" / "raw" / "penn_bonus"
RAW_ZIP = RAW_ROOT / "source" / "PA_ReempBonus.zip"
STAGING_ROOT = RAW_ROOT / "staging" / "cd"
RECORDS_TEXT = STAGING_ROOT / "data" / "Upjohn Institute Created files" / "recsfile.txt"
SURVEY_TEXT = STAGING_ROOT / "data" / "Upjohn Institute Created files" / "survfile.txt"
QUALIFICATION_RESULT = ROOT / "V12_QUALIFICATION_RESULT.json"
SOURCE_MANIFEST = ROOT / "manifests" / "V12_SOURCE_MANIFEST.json"
SCHEMA_AUDIT = ROOT / "manifests" / "V12_SCHEMA_AUDIT.json"

EXPECTED_RAW_SHA256 = "9036c9a82a5ab69b580b6646a3749019924442b7c6d10e4224ab0b910a95ef53"
EXPECTED_RAW_BYTES = 38_555_725
EXPECTED_RECORDS_HEADER_SHA256 = (
    "c8eaffadb1d75d647b964521704535c73dca5d8e260960b33af6c9e159858615"
)
EXPECTED_SURVEY_HEADER_SHA256 = (
    "c29e3aa0530e6b7b515bf1481473894e33c0c25217d9e71a4221639294e84508"
)
EXPECTED_ARCHIVE_ENTRIES = 19

IMMUTABLE_COMMITS = (
    "0fa794497dcea419a9322b70e5f69291a41d3c2c",
    "e4fefa96c0334971413fa3b73104158585edb5fb",
    "546f98d426b4979290db020e6e8c07ad482de143",
)
IMMUTABLE_PATHS = (
    (
        "0fa794497dcea419a9322b70e5f69291a41d3c2c",
        "benchmarks/ecommerce_decision_layer_v8_hillstrom_proof",
    ),
    (
        "e4fefa96c0334971413fa3b73104158585edb5fb",
        "benchmarks/ecommerce_decision_layer_v9_concealing_prices",
    ),
    (
        "546f98d426b4979290db020e6e8c07ad482de143",
        "benchmarks/ecommerce_decision_layer_v10_mtlift",
    ),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def header(path: Path) -> tuple[list[str], str]:
    with path.open("rb") as handle:
        raw = handle.readline()
    columns = next(csv.reader([raw.decode("latin1")]))
    return columns, hashlib.sha256(raw).hexdigest()


def newline_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def verify_raw_source() -> None:
    if RAW_ZIP.stat().st_size != EXPECTED_RAW_BYTES:
        raise RuntimeError("V12 official ZIP byte-size mismatch")
    if sha256(RAW_ZIP) != EXPECTED_RAW_SHA256:
        raise RuntimeError("V12 official ZIP SHA-256 mismatch")
    if RAW_ZIP.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("V12 official ZIP is writable")
    with zipfile.ZipFile(RAW_ZIP) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("V12 official ZIP CRC validation failed")
        if len(archive.infolist()) != EXPECTED_ARCHIVE_ENTRIES:
            raise RuntimeError("Unexpected V12 archive entry count")
        for item in archive.infolist():
            target = (Path("/") / item.filename).resolve()
            if not target.is_relative_to(Path("/")) or ".." in Path(item.filename).parts:
                raise RuntimeError(f"Unsafe V12 archive path: {item.filename}")


def verify_schema_without_outcomes() -> dict[str, Any]:
    records_columns, records_hash = header(RECORDS_TEXT)
    survey_columns, survey_hash = header(SURVEY_TEXT)
    if records_hash != EXPECTED_RECORDS_HEADER_SHA256:
        raise RuntimeError("V12 records header mismatch")
    if survey_hash != EXPECTED_SURVEY_HEADER_SHA256:
        raise RuntimeError("V12 survey header mismatch")
    if len(records_columns) != 189 or newline_count(RECORDS_TEXT) != 17_514:
        raise RuntimeError("V12 records metadata mismatch")
    if len(survey_columns) != 641 or newline_count(SURVEY_TEXT) != 5_679:
        raise RuntimeError("V12 survey metadata mismatch")
    if "id" in records_columns or records_columns[5] != "tg":
        raise RuntimeError("Unexpected V12 records identity/assignment schema")
    if survey_columns[0] != "id" or survey_columns[6] != "tg":
        raise RuntimeError("Unexpected V12 survey identity/assignment schema")
    return {
        "records_columns": records_columns,
        "records_observations": newline_count(RECORDS_TEXT) - 1,
        "survey_columns": survey_columns,
        "survey_observations": newline_count(SURVEY_TEXT) - 1,
    }


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )


def verify_immutable_history() -> None:
    for commit in IMMUTABLE_COMMITS:
        if _git("merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
            raise RuntimeError(f"Immutable commit is not an ancestor: {commit}")
    for commit, path in IMMUTABLE_PATHS:
        if _git("diff", "--quiet", commit, "HEAD", "--", path).returncode != 0:
            raise RuntimeError(f"Immutable path changed after {commit}: {path}")


def verify_outcome_isolation() -> dict[str, Any]:
    result = load_json(QUALIFICATION_RESULT)
    access = result["access_control"]
    if any(access.values()):
        raise RuntimeError("V12 qualification is not outcome-isolated")
    prohibited = (
        "V12_PREREGISTRATION.md",
        "V12_DEVELOPMENT_TOURNAMENT.md",
        "V12_FREEZE_MANIFEST.json",
        "V12_VALIDATION_RESULT.json",
        "POST_REVEAL_QA.json",
    )
    if any((ROOT / name).exists() for name in prohibited):
        raise RuntimeError("Downstream V12 artifact exists after qualification stop")
    return result


def verify_qualification_checkpoint() -> dict[str, Any]:
    verify_raw_source()
    verify_schema_without_outcomes()
    verify_immutable_history()
    result = verify_outcome_isolation()
    if result["final_status"] != "V12_DATA_NOT_CAUSALLY_QUALIFIED":
        raise RuntimeError("Unexpected V12 qualification status")
    if result["qualified"]:
        raise RuntimeError("V12 records without claimant ID cannot be qualified")
    return result
