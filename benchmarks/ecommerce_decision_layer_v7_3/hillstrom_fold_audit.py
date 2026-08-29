"""Diagnostic-only reconstruction of the immutable V7.2 Hillstrom folds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent
DEVELOPMENT = Path("data/processed/hillstrom/v7_2/development.parquet")
OUTPUT = ROOT / "results/hillstrom_v72_fold_forensics.json"
REPORT = ROOT / "V7_3_STABILITY_GATE_AUDIT.md"
PRIMARY_COST = 0.05
FOLDS = 5
PRETREATMENT_NUMERIC = ("recency", "history", "mens", "womens", "newbie")


def _folds(unit_hash: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            int(hashlib.sha256(f"hillstrom-static\0{value}".encode()).hexdigest()[:8], 16) % FOLDS
            for value in unit_hash
        ],
        dtype=int,
    )


def _smd(treated: np.ndarray, control: np.ndarray) -> float:
    pooled = float(np.sqrt((treated.var(ddof=1) + control.var(ddof=1)) / 2))
    return 0.0 if pooled == 0 else float((treated.mean() - control.mean()) / pooled)


def _fold_row(frame: pd.DataFrame, fold: int) -> dict[str, Any]:
    subset = frame[frame["fold"] == fold]
    treated = subset[subset["segment"] == "Mens E-Mail"]
    control = subset[subset["segment"] == "No E-Mail"]
    yt, yc = treated["spend"].to_numpy(float), control["spend"].to_numpy(float)
    gross = float(yt.mean() - yc.mean())
    net = gross - PRIMARY_COST
    se = float(np.sqrt(yt.var(ddof=1) / len(yt) + yc.var(ddof=1) / len(yc)))
    contributions = np.concatenate((yt / len(yt), -yc / len(yc)))
    order = np.argsort(np.abs(contributions))[::-1]

    def leave_top(k: int) -> float:
        removed_t = np.zeros(len(yt), dtype=bool)
        removed_c = np.zeros(len(yc), dtype=bool)
        for position in order[:k]:
            if position < len(yt):
                removed_t[position] = True
            else:
                removed_c[position - len(yt)] = True
        return float(yt[~removed_t].mean() - yc[~removed_c].mean() - PRIMARY_COST)

    arm: dict[str, Any] = {}
    for label, values in (("Mens E-Mail", yt), ("No E-Mail", yc)):
        arm[label] = {
            "n": len(values),
            "purchase_count": int(np.sum(values > 0)),
            "purchase_rate": float(np.mean(values > 0)),
            "total_spend": float(values.sum()),
            "gross_spend_mean": float(values.mean()),
            "net_value_mean": float(
                values.mean() - (PRIMARY_COST if label == "Mens E-Mail" else 0)
            ),
            "maximum_observation": float(values.max()),
            "effective_sample_size": len(values),
        }
    balance = {
        column: _smd(treated[column].to_numpy(float), control[column].to_numpy(float))
        for column in PRETREATMENT_NUMERIC
    }
    return {
        "fold": fold,
        "fold_size": len(subset),
        "arms": arm,
        "gross_difference_in_means": gross,
        "net_difference_in_means": net,
        "standard_error": se,
        "lower_95": net - float(norm.ppf(0.975)) * se,
        "upper_95": net + float(norm.ppf(0.975)) * se,
        "largest_absolute_observation_contribution": float(np.abs(contributions[order[0]])),
        "top_1_absolute_contribution": float(np.sum(np.abs(contributions[order[:1]]))),
        "top_5_absolute_contribution": float(np.sum(np.abs(contributions[order[:5]]))),
        "top_10_absolute_contribution": float(np.sum(np.abs(contributions[order[:10]]))),
        "leave_largest_net": leave_top(1),
        "leave_top_5_net": leave_top(5),
        "leave_top_10_net": leave_top(10),
        "max_absolute_numeric_smd": float(max(abs(value) for value in balance.values())),
        "numeric_smd": balance,
    }


def run() -> dict[str, Any]:
    frame = pd.read_parquet(DEVELOPMENT)
    pair = frame[frame["segment"].isin(("Mens E-Mail", "No E-Mail"))].copy()
    pair["fold"] = _folds(pair["unit_hash"].to_numpy(str))
    rows = [_fold_row(pair, fold) for fold in range(FOLDS)]
    all_net = np.asarray([row["net_difference_in_means"] for row in rows])
    leave_fold_out = []
    for fold in range(FOLDS):
        subset = pair[pair["fold"] != fold]
        yt = subset.loc[subset["segment"] == "Mens E-Mail", "spend"].to_numpy(float)
        yc = subset.loc[subset["segment"] == "No E-Mail", "spend"].to_numpy(float)
        leave_fold_out.append(float(yt.mean() - yc.mean() - PRIMARY_COST))
    result = {
        "status": "DIAGNOSTIC_ONLY_NO_GATE_CHANGE",
        "v7_2_reference_commit": "3ec80610c1cb990a9440b67ec60b2ab7ad75cc57",
        "hillstrom_status": "DEVELOPMENT_CONSUMED",
        "validation_opened": False,
        "sealed_test_used": False,
        "fold_count": FOLDS,
        "split_method": "sha256('hillstrom-static\\0' + development unit hash) modulo 5",
        "stratification": "none; deterministic hash folds",
        "primary_cost": PRIMARY_COST,
        "folds": rows,
        "leave_one_fold_out_net": leave_fold_out,
        "gate_definition": {
            "global_adjusted_lower_95_positive": True,
            "positive_fold_count_min": 4,
            "all_leave_one_fold_out_positive": True,
            "minimum_fold_net": -0.05,
            "veto_reason": (
                "any fold below -0.05 fails even when four folds and every "
                "leave-one-out are positive"
            ),
        },
        "observed_positive_fold_count": int(np.sum(all_net > 0)),
        "observed_minimum_fold_net": float(all_net.min()),
        "observed_all_leave_one_out_positive": bool(np.all(np.asarray(leave_fold_out) > 0)),
        "gate_pass": bool(
            np.sum(all_net > 0) >= 4
            and all_net.min() >= -0.05
            and np.all(np.asarray(leave_fold_out) > 0)
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = [
        "# V7.3 Audit of the Existing Hillstrom Stability Gate",
        "",
        (
            "Diagnostic only. Hillstrom remains DEVELOPMENT-CONSUMED; VALIDATION and "
            "SEALED_TEST were not read."
        ),
        "",
        (
            "The V7.2 rule uses five unstratified deterministic SHA-256 folds. It requires "
            "at least four positive folds, every leave-one-fold-out estimate positive, and "
            "no individual fold below -$0.05 net. Thus one fold below -$0.05 vetoes the "
            "action even when the aggregate adjusted lower bound is positive."
        ),
        "",
        (
            "| Fold | Mens n/purchases/total | Control n/purchases/total | Net DIM | "
            "SE | 95% CI | Max | Leave top 1/5/10 | Max |SMD| |"
        ),
        "|---:|---|---|---:|---:|---|---:|---|---:|",
    ]
    for row in rows:
        mens, control = row["arms"]["Mens E-Mail"], row["arms"]["No E-Mail"]
        lines.append(
            f"| {row['fold']} | {mens['n']}/{mens['purchase_count']}/${mens['total_spend']:.2f} | "
            f"{control['n']}/{control['purchase_count']}/${control['total_spend']:.2f} | "
            f"${row['net_difference_in_means']:.4f} | ${row['standard_error']:.4f} | "
            f"[${row['lower_95']:.4f}, ${row['upper_95']:.4f}] | "
            f"${max(mens['maximum_observation'], control['maximum_observation']):.2f} | "
            f"${row['leave_largest_net']:.4f}/${row['leave_top_5_net']:.4f}/"
            f"${row['leave_top_10_net']:.4f} | {row['max_absolute_numeric_smd']:.4f} |"
        )
    lines.extend(
        [
            "",
            (
                f"Observed positive folds: `{result['observed_positive_fold_count']}/5`; "
                f"minimum fold net: `${result['observed_minimum_fold_net']:.6f}`; every "
                "leave-one-fold-out estimate positive: "
                f"`{result['observed_all_leave_one_out_positive']}`. The fixed gate "
                "therefore fails."
            ),
            "",
            (
                "Top-observation contributions, purchase rates, arm-level means, ESS, numeric "
                "balance, and leave-top-k diagnostics are retained in "
                "`results/hillstrom_v72_fold_forensics.json`. No diagnostic is used to change "
                "V7.2 or select a V7.3 threshold."
            ),
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
