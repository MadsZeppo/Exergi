"""Development-only V9 analysis. This module has no held-out outcome path."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .estimators import (
    Estimate,
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
    RESULTS,
    STUDY1_RAW,
    STUDY3_RAW,
    assert_split_integrity,
    stable_unit_hash,
    study3_split,
)


@dataclass(frozen=True)
class Study3Development:
    unit_hash: np.ndarray
    treatment: np.ndarray
    units: np.ndarray
    revenue: np.ndarray


def _to_float(value: str, field: str) -> float:
    if value == "":
        raise ValueError(f"missing DEVELOPMENT outcome: {field}")
    parsed = float(value)
    if not np.isfinite(parsed):
        raise ValueError(f"non-finite DEVELOPMENT outcome: {field}")
    return parsed


def load_study1_development() -> dict[int, dict[int, dict[str, float]]]:
    with STUDY1_RAW.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        identifiers = [(int(row["date_id"]), int(row["treatment"])) for row in reader]
    development_dates = set(sorted({date for date, _ in identifiers})[:28])
    rows: dict[int, dict[int, dict[str, float]]] = defaultdict(dict)
    with STUDY1_RAW.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            date_id = int(row["date_id"])
            if date_id not in development_dates:
                continue
            treatment = int(row["treatment"])
            rows[date_id][treatment] = {
                "revenue": _to_float(row["revenues"], "revenues"),
                "users": _to_float(row["users"], "users"),
                "units": _to_float(row["units_sold"], "units_sold"),
                "purchase": _to_float(row["prob_sale"], "prob_sale"),
            }
    if len(rows) != 28 or any(set(arms) != {0, 1} for arms in rows.values()):
        raise ValueError("Study 1 DEVELOPMENT pairing failed")
    return dict(rows)


def load_study3_development() -> Study3Development:
    hashes: list[str] = []
    treatments: list[int] = []
    units: list[float] = []
    revenues: list[float] = []
    with STUDY3_RAW.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            unit_hash = stable_unit_hash("study3-recipient", row["user_id"])
            if study3_split(unit_hash) != "DEVELOPMENT":
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


def _study1_contrasts(
    rows: dict[int, dict[int, dict[str, float]]], numerator: str, denominator: str | None
) -> np.ndarray:
    values = []
    for date_id in sorted(rows):
        control = rows[date_id][0][numerator]
        treated = rows[date_id][1][numerator]
        if denominator is not None:
            control /= rows[date_id][0][denominator]
            treated /= rows[date_id][1][denominator]
        values.append(treated - control)
    return np.asarray(values)


def _selection(primary: Estimate) -> str:
    if not np.isfinite(primary.point) or not np.isfinite(primary.standard_error):
        return "NOT_ENOUGH_EVIDENCE"
    if primary.point > 0 and primary.upper_95 > 0:
        return "TEST_DELAYED_PRICE"
    if primary.point < 0:
        return "AVOID_DELAYED_PRICE"
    return "NOT_ENOUGH_EVIDENCE"


def _estimate_dict(estimate: Estimate) -> dict[str, float | int | str]:
    return asdict(estimate)


def _fold_estimates(data: Study3Development) -> list[dict[str, float | int | str]]:
    folds = np.asarray([int(value[:8], 16) % 5 for value in data.unit_hash])
    return [
        {
            "fold": fold,
            **_estimate_dict(
                difference_in_means(data.revenue[folds == fold], data.treatment[folds == fold])
            ),
        }
        for fold in range(5)
    ]


def analyze_development(*, write: bool = True) -> dict[str, Any]:
    split = assert_split_integrity()
    config = json.loads(CONFIG.read_text())
    s1 = load_study1_development()
    s3 = load_study3_development()
    if len(s3.revenue) != split["study3"]["row_counts"]["DEVELOPMENT"]:
        raise ValueError("Study 3 DEVELOPMENT row-count mismatch")

    s1_primary_values = _study1_contrasts(s1, "revenue", "users")
    s1_primary = paired_difference(s1_primary_values)
    s1_units = paired_difference(_study1_contrasts(s1, "units", "users"))
    s1_purchase = paired_difference(_study1_contrasts(s1, "purchase", None))
    s1_log_revenue = paired_difference(
        np.log1p(
            np.asarray([s1[date][1]["revenue"] for date in sorted(s1)])
        )
        - np.log1p(np.asarray([s1[date][0]["revenue"] for date in sorted(s1)]))
    )

    s3_primary = difference_in_means(s3.revenue, s3.treatment)
    s3_units = difference_in_means(s3.units, s3.treatment)
    s3_purchase = difference_in_means((s3.units > 0).astype(float), s3.treatment)
    s3_log_revenue = difference_in_means(np.log1p(s3.revenue), s3.treatment)
    leave_top_cap = float(np.quantile(s3.revenue, 1 - config["robustness"]["leave_top_fraction"]))
    leave_top_mask = s3.revenue <= leave_top_cap
    s3_leave_top = difference_in_means(
        s3.revenue[leave_top_mask], s3.treatment[leave_top_mask]
    )

    bootstrap_replicates = int(config["robustness"]["bootstrap_replicates"])
    permutation_replicates = int(config["robustness"]["permutation_replicates"])
    bootstrap_seed = int(config["random_seeds"]["bootstrap"])
    permutation_seed = int(config["random_seeds"]["randomization_inference"])
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "V9_DEVELOPMENT_COMPLETE_VALIDATION_CLOSED",
        "preregistration_commit": "4638172",
        "published_effects_used_for_selection": False,
        "study1": {
            "classification": "AGGREGATE_RANDOMIZED_FIELD_EVIDENCE",
            "development_dates": 28,
            "development_rows": 56,
            "primary": _estimate_dict(s1_primary),
            "selection": _selection(s1_primary),
            "break_even_incremental_action_cost_ars_per_assigned_visitor": max(
                0.0, s1_primary.point
            ),
            "secondary": {
                "units_per_assigned_visitor": _estimate_dict(s1_units),
                "daily_purchase_probability": _estimate_dict(s1_purchase),
                "log1p_daily_revenue": _estimate_dict(s1_log_revenue),
                "paired_bootstrap": paired_bootstrap(
                    s1_primary_values, replicates=bootstrap_replicates, seed=bootstrap_seed
                ),
                "paired_sign_randomization_p_value": paired_sign_permutation_p_value(
                    s1_primary_values,
                    replicates=permutation_replicates,
                    seed=permutation_seed,
                ),
                "first_half": _estimate_dict(paired_difference(s1_primary_values[:14])),
                "second_half": _estimate_dict(paired_difference(s1_primary_values[14:])),
            },
        },
        "study3": {
            "classification": "INDIVIDUAL_RANDOMIZED_FIELD_EVIDENCE",
            "development_rows": len(s3.revenue),
            "arm_counts": {
                "immediate": int(np.sum(s3.treatment == 0)),
                "delayed": int(np.sum(s3.treatment == 1)),
            },
            "primary": _estimate_dict(s3_primary),
            "selection": _selection(s3_primary),
            "break_even_incremental_action_cost_ars_per_recipient": max(0.0, s3_primary.point),
            "secondary": {
                "units": _estimate_dict(s3_units),
                "purchase_probability": _estimate_dict(s3_purchase),
                "log1p_revenue": _estimate_dict(s3_log_revenue),
                "leave_top_0_1_percent_cap_from_development": leave_top_cap,
                "leave_top_0_1_percent": _estimate_dict(s3_leave_top),
                "arm_stratified_bootstrap": arm_stratified_bootstrap(
                    s3.revenue,
                    s3.treatment,
                    replicates=bootstrap_replicates,
                    seed=bootstrap_seed + 1,
                ),
                "assignment_randomization_p_value": permutation_p_value(
                    s3.revenue,
                    s3.treatment,
                    replicates=permutation_replicates,
                    seed=permutation_seed + 1,
                ),
                "fold_estimates": _fold_estimates(s3),
            },
            "diagnostics": {
                "srm_p_value": srm_p_value(s3.treatment),
                "revenue_heavy_tail": heavy_tail_diagnostics(s3.revenue),
                "outcome_missing_count": 0,
                "duplicate_recipient_count": 0,
            },
        },
        "validation_opened": False,
        "sealed_test_opened": False,
    }
    if write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "V9_DEVELOPMENT_RESULT.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
    return result


if __name__ == "__main__":
    print(json.dumps(analyze_development(), indent=2, sort_keys=True))
