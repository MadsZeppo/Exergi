"""One-shot V9 validation runner with no sealed-test fallback."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .development import Study3Development, _study1_contrasts, _to_float
from .estimators import (
    arm_stratified_bootstrap,
    difference_in_means,
    heavy_tail_diagnostics,
    paired_bootstrap,
    paired_difference,
    paired_sign_permutation_p_value,
    permutation_p_value,
    srm_p_value,
)
from .integrity import (
    CONFIG,
    DEVELOPMENT_RESULT,
    FREEZE_MANIFEST,
    RESULTS,
    STUDY1_RAW,
    STUDY3_RAW,
    IntegrityError,
    assert_split_integrity,
    load_json,
    sha256_file,
    stable_unit_hash,
    study3_split,
    verify_frozen_sources,
)


@dataclass(frozen=True)
class OneShotFiles:
    reveal_start: Path
    result: Path
    consumed: Path
    sufficient_statistics: Path


def study_files(study: str) -> OneShotFiles:
    directory = RESULTS / study
    return OneShotFiles(
        reveal_start=directory / "V9_REVEAL_STARTED.json",
        result=directory / "V9_VALIDATION_RESULT.json",
        consumed=directory / "V9_VALIDATION_CONSUMED.json",
        sufficient_statistics=directory / "V9_VALIDATION_SUFFICIENT_STATISTICS.json",
    )


def begin_reveal(files: OneShotFiles, payload: dict[str, Any]) -> None:
    files.reveal_start.parent.mkdir(parents=True, exist_ok=True)
    if files.reveal_start.exists() or files.result.exists() or files.consumed.exists():
        raise IntegrityError("V9 validation has already been consumed")
    record = {
        **payload,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "irreversible": True,
    }
    with files.reveal_start.open("x") as handle:
        handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")


def _require_freeze() -> dict[str, Any]:
    if not FREEZE_MANIFEST.exists():
        raise IntegrityError("V9 validation requires committed freeze")
    freeze = load_json(FREEZE_MANIFEST)
    verify_frozen_sources(freeze)
    assert_split_integrity()
    return freeze


def dry_run() -> dict[str, Any]:
    freeze = _require_freeze()
    lifecycle_clear = all(
        not path.exists()
        for study in ("study1", "study3")
        for path in asdict(study_files(study)).values()
    )
    if not lifecycle_clear:
        raise IntegrityError("V9 reveal lifecycle is not clear")
    result = {
        "status": "V9_PRE_REVEAL_DRY_RUN_PASS",
        "source_tree_sha256": freeze["source_tree_sha256"],
        "split_manifest_sha256": freeze["split_manifest_sha256"],
        "development_result_sha256": sha256_file(DEVELOPMENT_RESULT),
        "study1_expected_validation_dates": 28,
        "study3_expected_validation_rows": freeze["studies"]["study3"][
            "expected_validation_rows"
        ],
        "outcome_accessed": False,
        "sealed_fallback_available": False,
        "lifecycle_clear": lifecycle_clear,
    }
    (RESULTS / "V9_PRE_REVEAL_DRY_RUN.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def load_study1_validation() -> dict[int, dict[int, dict[str, float]]]:
    with STUDY1_RAW.open(newline="", encoding="utf-8-sig") as handle:
        identifiers = [
            (int(row["date_id"]), int(row["treatment"])) for row in csv.DictReader(handle)
        ]
    validation_dates = set(sorted({date for date, _ in identifiers})[28:])
    rows: dict[int, dict[int, dict[str, float]]] = defaultdict(dict)
    with STUDY1_RAW.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            date_id = int(row["date_id"])
            if date_id not in validation_dates:
                continue
            treatment = int(row["treatment"])
            rows[date_id][treatment] = {
                "revenue": _to_float(row["revenues"], "revenues"),
                "users": _to_float(row["users"], "users"),
                "units": _to_float(row["units_sold"], "units_sold"),
                "purchase": _to_float(row["prob_sale"], "prob_sale"),
            }
    if len(rows) != 28 or any(set(arms) != {0, 1} for arms in rows.values()):
        raise IntegrityError("Study 1 validation pairing failed")
    return dict(rows)


def load_study3_validation() -> Study3Development:
    hashes: list[str] = []
    treatments: list[int] = []
    units: list[float] = []
    revenues: list[float] = []
    with STUDY3_RAW.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            unit_hash = stable_unit_hash("study3-recipient", row["user_id"])
            if study3_split(unit_hash) != "VALIDATION":
                continue
            hashes.append(unit_hash)
            treatments.append(int(row["treatment"]))
            units.append(_to_float(row["units_sold"], "units_sold"))
            revenues.append(_to_float(row["revenues"], "revenues"))
    return Study3Development(
        unit_hash=np.asarray(hashes),
        treatment=np.asarray(treatments, dtype=np.int8),
        units=np.asarray(units),
        revenue=np.asarray(revenues),
    )


def _sufficient_stats(outcome: np.ndarray, treatment: np.ndarray) -> dict[str, Any]:
    values = {}
    for arm, label in ((0, "immediate"), (1, "delayed")):
        selected = outcome[treatment == arm]
        values[label] = {
            "n": len(selected),
            "sum": float(selected.sum()),
            "sum_squares": float(np.square(selected).sum()),
        }
    return values


def _write_once(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise IntegrityError(f"immutable V9 artifact already exists: {path.name}")
    with path.open("x") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _finish(files: OneShotFiles, result: dict[str, Any], sufficient: dict[str, Any]) -> None:
    _write_once(files.sufficient_statistics, sufficient)
    _write_once(files.result, result)
    _write_once(
        files.consumed,
        {
            "status": "V9_VALIDATION_PERMANENTLY_CONSUMED",
            "consumed_at_utc": datetime.now(UTC).isoformat(),
            "result_sha256": sha256_file(files.result),
            "sufficient_statistics_sha256": sha256_file(files.sufficient_statistics),
            "second_reveal_permitted": False,
        },
    )


def reveal_study1(freeze: dict[str, Any]) -> dict[str, Any]:
    files = study_files("study1")
    begin_reveal(
        files,
        {
            "study": "study1",
            "frozen_policy": freeze["studies"]["study1"]["policy"],
            "freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST),
        },
    )
    rows = load_study1_validation()
    config = load_json(CONFIG)
    primary_values = _study1_contrasts(rows, "revenue", "users")
    primary = paired_difference(primary_values)
    status = (
        "CONFIRMED_ACTION"
        if primary.point > 0 and primary.lower_95 > 0
        else "CONTRADICTED"
        if primary.point < 0
        else "INCONCLUSIVE"
    )
    result: dict[str, Any] = {
        "study": "study1",
        "status": status,
        "frozen_policy": "TEST_DELAYED_PRICE",
        "context": "ordinary online store",
        "primary": asdict(primary),
        "claim_authority": "REAL_RANDOMIZED_AGGREGATE_REVENUE",
        "secondary": {
            "units_per_assigned_visitor": asdict(
                paired_difference(_study1_contrasts(rows, "units", "users"))
            ),
            "daily_purchase_probability": asdict(
                paired_difference(_study1_contrasts(rows, "purchase", None))
            ),
            "paired_bootstrap": paired_bootstrap(
                primary_values,
                replicates=int(config["robustness"]["bootstrap_replicates"]),
                seed=int(config["random_seeds"]["bootstrap"]) + 10,
            ),
            "paired_sign_randomization_p_value": paired_sign_permutation_p_value(
                primary_values,
                replicates=int(config["robustness"]["permutation_replicates"]),
                seed=int(config["random_seeds"]["randomization_inference"]) + 10,
            ),
        },
        "action_cost_observed": False,
        "break_even_incremental_action_cost_ars_per_assigned_visitor": max(
            0.0, primary.point
        ),
        "validation_consumed": True,
        "sealed_test_opened": False,
    }
    sufficient = {
        "study": "study1",
        "date_count": len(primary_values),
        "contrast_sum": float(primary_values.sum()),
        "contrast_sum_squares": float(np.square(primary_values).sum()),
    }
    _finish(files, result, sufficient)
    return result


def reveal_study3(freeze: dict[str, Any]) -> dict[str, Any]:
    files = study_files("study3")
    begin_reveal(
        files,
        {
            "study": "study3",
            "frozen_policy": freeze["studies"]["study3"]["policy"],
            "freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST),
        },
    )
    data = load_study3_validation()
    expected = freeze["studies"]["study3"]["expected_validation_rows"]
    if len(data.revenue) != expected:
        raise IntegrityError("Study 3 validation row-count mismatch")
    config = load_json(CONFIG)
    primary = difference_in_means(data.revenue, data.treatment)
    status = (
        "CONFIRMED_AVOID"
        if primary.point < 0 and primary.upper_95 < 0
        else "CONTRADICTED"
        if primary.point > 0
        else "INCONCLUSIVE"
    )
    development = load_json(DEVELOPMENT_RESULT)
    cap = development["study3"]["secondary"][
        "leave_top_0_1_percent_cap_from_development"
    ]
    leave_top = data.revenue <= cap
    result: dict[str, Any] = {
        "study": "study3",
        "status": status,
        "frozen_policy": "AVOID_DELAYED_PRICE",
        "context": "discount sales-email flyer",
        "primary": asdict(primary),
        "claim_authority": "REAL_RANDOMIZED_SALES_REVENUE",
        "secondary": {
            "units": asdict(difference_in_means(data.units, data.treatment)),
            "purchase_probability": asdict(
                difference_in_means((data.units > 0).astype(float), data.treatment)
            ),
            "log1p_revenue": asdict(
                difference_in_means(np.log1p(data.revenue), data.treatment)
            ),
            "leave_top_using_development_cap": asdict(
                difference_in_means(data.revenue[leave_top], data.treatment[leave_top])
            ),
            "arm_stratified_bootstrap": arm_stratified_bootstrap(
                data.revenue,
                data.treatment,
                replicates=int(config["robustness"]["bootstrap_replicates"]),
                seed=int(config["random_seeds"]["bootstrap"]) + 11,
            ),
            "assignment_randomization_p_value": permutation_p_value(
                data.revenue,
                data.treatment,
                replicates=int(config["robustness"]["permutation_replicates"]),
                seed=int(config["random_seeds"]["randomization_inference"]) + 11,
            ),
        },
        "diagnostics": {
            "srm_p_value": srm_p_value(data.treatment),
            "revenue_heavy_tail": heavy_tail_diagnostics(data.revenue),
            "outcome_missing_count": 0,
        },
        "action_cost_observed": False,
        "break_even_harm_avoided_ars_per_recipient": max(0.0, -primary.point),
        "validation_consumed": True,
        "sealed_test_opened": False,
    }
    sufficient = {
        "study": "study3",
        "revenue": _sufficient_stats(data.revenue, data.treatment),
        "units": _sufficient_stats(data.units, data.treatment),
        "purchase": _sufficient_stats((data.units > 0).astype(float), data.treatment),
    }
    _finish(files, result, sufficient)
    return result


def reveal_all() -> dict[str, Any]:
    freeze = _require_freeze()
    study1 = reveal_study1(freeze)
    study3 = reveal_study3(freeze)
    return {"study1": study1, "study3": study3}


if __name__ == "__main__":
    print(json.dumps(reveal_all(), indent=2, sort_keys=True))
