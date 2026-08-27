"""Development-only OPE validation on publisher Open Bandit quick data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from commercial_twin.research_v1 import (
    doubly_robust_policy_value,
    effective_sample_size,
    importance_weights,
    ips,
    snips,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/open_bandit/zr-obp-master/obd"
OUT = ROOT / "benchmarks/customer_twin_research_v1/open_bandit"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> None:
    random_path, bts_path = RAW / "random/all/all.csv", RAW / "bts/all/all.csv"
    random = pd.read_csv(random_path, index_col=0)
    bts = pd.read_csv(bts_path, index_col=0)
    OUT.mkdir(parents=True, exist_ok=True)
    target = (bts.groupby(["position", "item_id"]).size() / bts.groupby("position").size()).rename(
        "target_probability"
    )
    random = random.join(target, on=["position", "item_id"])
    random.target_probability = random.target_probability.fillna(0)
    weights = importance_weights(
        random.propensity_score.to_numpy(float), random.target_probability.to_numpy(float)
    )
    # Smoothed action-position reward model fitted only on the random-policy log.
    global_reward = float(random.click.mean())
    aggregate = random.groupby(["position", "item_id"]).click.agg(["sum", "count"])
    q = ((aggregate["sum"] + 20 * global_reward) / (aggregate["count"] + 20)).rename("q")
    factual_q = random.join(q, on=["position", "item_id"])["q"].fillna(global_reward).to_numpy()
    target_q = []
    for position in random.position:
        probability = target.loc[position]
        reward = q.loc[position].reindex(probability.index).fillna(global_reward)
        target_q.append(float(np.sum(probability.to_numpy() * reward.to_numpy())))
    target_q_array = np.asarray(target_q)
    reward = random.click.to_numpy(float)
    values = {
        "IPS": ips(reward, weights),
        "SNIPS": snips(reward, weights),
        "DR": doubly_robust_policy_value(reward, weights, factual_q, target_q_array),
    }
    empirical = float(bts.click.mean())
    rows = [
        {
            "estimator": name,
            "estimated_value": value,
            "empirical_target_value": empirical,
            "absolute_error": abs(value - empirical),
            "relative_error": abs(value - empirical) / max(empirical, 1e-12),
            "ess": effective_sample_size(weights),
            "ci": "NOT_COMPUTED_QUICK",
        }
        for name, value in values.items()
    ]
    pd.DataFrame(rows).to_csv(OUT / "ope_estimators.csv", index=False)
    diagnostics = {
        "rows": len(random),
        "ess": effective_sample_size(weights),
        "ess_fraction": effective_sample_size(weights) / len(random),
        "max_weight": float(weights.max()),
        "p95": float(np.quantile(weights, 0.95)),
        "p99": float(np.quantile(weights, 0.99)),
        "p999": float(np.quantile(weights, 0.999)),
        "unsupported_fraction": float(np.mean(random.target_probability == 0)),
    }
    pd.DataFrame([diagnostics]).to_csv(OUT / "weight_diagnostics.csv", index=False)
    provenance = {
        "canonical_source": "https://github.com/st-tech/zr-obp/tree/master/obd",
        "archive_sha256": sha(ROOT / "data/raw/open_bandit/zr-obp-master.zip"),
        "random_all_sha256": sha(random_path),
        "bts_all_sha256": sha(bts_path),
        "data_scope": "publisher quick data: 10,000 records per policy/campaign",
        "full_26m_dataset_acquired": False,
        "official_status": "UNPROVEN",
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (OUT / "quick_metrics.json").write_text(
        json.dumps(
            {
                "values": values,
                "empirical_target_value": empirical,
                "weight_diagnostics": diagnostics,
                "official_freeze_written": False,
                "official_reveal_marker_written": False,
                "interpretation": (
                    "pipeline validation only; target policy reconstructed marginally"
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "REPORT.md").write_text(
        "# Open Bandit OPE\n\nStatus: **UNPROVEN**. Publisher quick data validated IPS, "
        "SNIPS, DR and ESS plumbing. The full 26M-row official protocol was not executed, "
        "and the quick target policy was reconstructed marginally rather than from exact "
        "per-context target probabilities. No official freeze or reveal exists.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
