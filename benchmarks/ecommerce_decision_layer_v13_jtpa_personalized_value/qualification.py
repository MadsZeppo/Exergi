from __future__ import annotations

import csv
import hashlib
import json
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
RAW_ZIP = WORKSPACE / "data" / "raw" / "jtpa" / "jtpa_national_evaluation.zip"
STAGING = WORKSPACE / "data" / "processed" / "jtpa"
BASELINE = STAGING / "baseline" / "expbif.dta"
OUTCOME_SCHEMA = STAGING / "outcome_schema"
TIMING_DICTIONARY = ROOT / "V13_VARIABLE_TIMING_DICTIONARY.csv"
QUALIFICATION_RESULT = ROOT / "V13_QUALIFICATION_RESULT.json"
SOURCE_MANIFEST = ROOT / "manifests" / "V13_SOURCE_MANIFEST.json"
QUALIFICATION_AUDIT = ROOT / "manifests" / "V13_QUALIFICATION_AUDIT.json"

EXPECTED_RAW_SHA256 = "3607617e265ec3eac11436f3f19a25e43e3ecf53ba6de6b98a9dede53cc3a76b"
EXPECTED_RAW_BYTES = 127_676_441
EXPECTED_ARCHIVE_ENTRIES = 388
EXPECTED_BASELINE_SHA256 = "decf5853ceeb60d6020412f778bba079c6c839276b432fdf725d3ae75cdcd3b0"
EXPECTED_EARNS_SHA256 = "0464adf2bf4c0a8418d3459f988992dc306b68e3f1b10ec6b0da62b1bbfc56e6"
EXPECTED_BOYS_SHA256 = "1cfbf385158d2ce4df2bd104eeb965b1d1d429f05fff045095c76c25568ee081"
EXPECTED_PPD_SHA256 = "d1f005cccacae0e9a22999cdb263c4ec9a9be332a7fd6282de373124ad0b02d8"
EXPECTED_TOTERNS_SHA256 = "87b565240405d3e5eb1b139831d8943818f0b9a813697cd6328aa0c7bd7d1a27"
EXPECTED_SCALEDUI_SHA256 = "ac0b4c26e41accea8d3906cf3fdce3a079c5fbf93da46144f0dd2db7ed35ef03"

EXPECTED_FULL_ROWS = 20_601
EXPECTED_MATURE_ROWS = 15_134
EXPECTED_TREATED_MATURE = 10_145
EXPECTED_CONTROL_MATURE = 4_989

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
    (
        "92b4765b6acf359bf8d5d921c74ad06b1685a6e6",
        "benchmarks/ecommerce_decision_layer_v12_penn_bonus",
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_raw_source() -> None:
    if RAW_ZIP.stat().st_size != EXPECTED_RAW_BYTES:
        raise RuntimeError("V13 official ZIP byte-size mismatch")
    if sha256(RAW_ZIP) != EXPECTED_RAW_SHA256:
        raise RuntimeError("V13 official ZIP SHA-256 mismatch")
    if RAW_ZIP.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("V13 official ZIP is writable")
    with zipfile.ZipFile(RAW_ZIP) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("V13 official ZIP CRC validation failed")
        if len(archive.infolist()) != EXPECTED_ARCHIVE_ENTRIES:
            raise RuntimeError("Unexpected V13 archive entry count")
        for item in archive.infolist():
            if ".." in Path(item.filename).parts or Path(item.filename).is_absolute():
                raise RuntimeError(f"Unsafe V13 archive path: {item.filename}")


def _normalized_ids(path: Path) -> pd.Series:
    # Outcome values remain closed: only the join key is materialized during qualification.
    frame = pd.read_stata(path, convert_categoricals=False, columns=["recid"])
    return (
        frame["recid"]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def verify_participant_contract() -> dict[str, Any]:
    expected_hashes = {
        BASELINE: EXPECTED_BASELINE_SHA256,
        OUTCOME_SCHEMA / "earns2.dta": EXPECTED_EARNS_SHA256,
        OUTCOME_SCHEMA / "boysern2.dta": EXPECTED_BOYS_SHA256,
        OUTCOME_SCHEMA / "ppd_dat.dta": EXPECTED_PPD_SHA256,
        OUTCOME_SCHEMA / "toterns.dta": EXPECTED_TOTERNS_SHA256,
        OUTCOME_SCHEMA / "analysis" / "scaledui.dta": EXPECTED_SCALEDUI_SHA256,
    }
    for path, expected in expected_hashes.items():
        if sha256(path) != expected:
            raise RuntimeError(f"V13 staged-file checksum mismatch: {path.name}")

    baseline = pd.read_stata(BASELINE, convert_categoricals=False)
    if len(baseline) != EXPECTED_FULL_ROWS or baseline["recid"].duplicated().any():
        raise RuntimeError("V13 baseline participant identity contract failed")
    if set(baseline["ra_stat"]) != {"1", "2"}:
        raise RuntimeError("Unexpected V13 assignment encoding")

    regular_ids = _normalized_ids(OUTCOME_SCHEMA / "earns2.dta")
    male_youth_arrestee_ids = _normalized_ids(OUTCOME_SCHEMA / "boysern2.dta")
    if regular_ids.duplicated().any() or male_youth_arrestee_ids.duplicated().any():
        raise RuntimeError("Duplicate participant in V13 mature outcome files")
    if set(regular_ids) & set(male_youth_arrestee_ids):
        raise RuntimeError("V13 mature outcome sources overlap")

    official_analysis_ids = set(regular_ids) | set(male_youth_arrestee_ids)
    scaled_ui_ids = set(_normalized_ids(OUTCOME_SCHEMA / "analysis" / "scaledui.dta"))
    mature_ids = official_analysis_ids & scaled_ui_ids
    if len(mature_ids) != EXPECTED_MATURE_ROWS:
        raise RuntimeError("Unexpected V13 mature outcome population")
    baseline_ids = set(baseline["recid"].astype(str).str.strip())
    if not mature_ids <= baseline_ids:
        raise RuntimeError("V13 mature outcome ID absent from baseline")

    mature = baseline[baseline["recid"].isin(mature_ids)]
    treated = int((mature["ra_stat"] == "1").sum())
    control = int((mature["ra_stat"] == "2").sum())
    if (treated, control) != (EXPECTED_TREATED_MATURE, EXPECTED_CONTROL_MATURE):
        raise RuntimeError("Unexpected V13 mature assignment counts")
    return {
        "full_rows": len(baseline),
        "full_unique_recid": baseline["recid"].nunique(),
        "mature_rows": len(mature),
        "mature_treated": treated,
        "mature_control": control,
        "mature_treatment_rate": treated / len(mature),
    }


def verify_timing_contract() -> None:
    allowed_timing = {
        "PRETREATMENT_ALLOWED",
        "ASSIGNMENT_ONLY",
        "OUTCOME_ONLY",
        "POST_TREATMENT_FORBIDDEN",
        "UNKNOWN_FORBIDDEN",
        "EVALUATOR_ONLY",
    }
    with TIMING_DICTIONARY.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 470:
        raise RuntimeError("V13 timing dictionary does not cover the analytic contract")
    if {row["timing_class"] for row in rows} - allowed_timing:
        raise RuntimeError("Unknown V13 timing class")
    for row in rows:
        if row["policy_status"] == "POLICY_ALLOWED" and row["timing_class"] != (
            "PRETREATMENT_ALLOWED"
        ):
            raise RuntimeError(f"Forbidden policy feature: {row['source']}::{row['variable']}")
    participation = [row for row in rows if row["source"] == "ppd_dat.dta"]
    if any(
        row["policy_status"] == "POLICY_ALLOWED" for row in participation
    ):
        raise RuntimeError("Actual participation leaked into V13 policy features")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=WORKSPACE,
        check=False,
        capture_output=True,
        text=True,
    )


def verify_immutable_history() -> None:
    for commit, path in IMMUTABLE_PATHS:
        if _git("merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
            raise RuntimeError(f"Immutable commit is not an ancestor: {commit}")
        if _git("diff", "--quiet", commit, "HEAD", "--", path).returncode != 0:
            raise RuntimeError(f"Immutable path changed after {commit}: {path}")


def verify_qualification_checkpoint() -> dict[str, Any]:
    verify_raw_source()
    verify_participant_contract()
    verify_timing_contract()
    verify_immutable_history()
    result = load_json(QUALIFICATION_RESULT)
    if result["qualification_status"] != "QUALIFIED_FOR_RANDOMIZED_EARNINGS_ONLY":
        raise RuntimeError("Unexpected V13 qualification status")
    if result["access_control"]["raw_outcome_values_analyzed"]:
        raise RuntimeError("V13 qualification crossed the outcome boundary")
    return result
