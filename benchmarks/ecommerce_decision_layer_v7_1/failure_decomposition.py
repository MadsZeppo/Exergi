"""Read-only decomposition of consumed V7 H-M heterogeneous worlds."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from benchmarks.ecommerce_decision_layer_v7.evaluation import UpliftModel, _dr_scores
from benchmarks.ecommerce_decision_layer_v7.packs import pack_specs
from benchmarks.ecommerce_decision_layer_v7.world import WorldFamily, WorldSpec, generate_world

V7_ROOT = Path(__file__).resolve().parents[1] / "ecommerce_decision_layer_v7"
V71_ROOT = Path(__file__).resolve().parent
OUTPUT = V71_ROOT / "results" / "v7_failure_decomposition.json"
REPORT = V71_ROOT / "V7_1_FAILURE_DECOMPOSITION.md"
MATERIALITY_CP_PER_ELIGIBLE_CUSTOMER = 0.10
FROZEN_MODEL = "forest_t_learner"
HETEROGENEOUS_FAMILIES = {
    WorldFamily.SPARSE_HETEROGENEITY,
    WorldFamily.QUALITATIVE_HETEROGENEITY,
}


@dataclass(frozen=True)
class DecompositionRow:
    world_id: str
    family: str
    classification: str
    full_oracle_increment: float
    observable_oracle_increment: float
    segment_oracle_increment: float
    frozen_forest_increment: float
    full_oracle_value_capture: float
    observable_oracle_value_capture: float
    forest_capture_of_observable_increment: float
    cate_variance: float
    economically_relevant_cate_variance: float
    positive_subgroup_prevalence: float
    incremental_cp_per_targeted_customer: float
    treatment_cost: float
    switching_cost: float
    sample_size: int
    effective_sample_size: float
    propensity_min: float
    propensity_max: float
    rate: float
    rate_lower: float
    autoc: float
    autoc_lower: float
    qini: float
    qini_lower: float
    personalization_promoted: bool
    reason_codes: tuple[str, ...]


def _policy_value(effect: np.ndarray, policy: np.ndarray) -> float:
    return float(np.mean(effect * np.asarray(policy, dtype=bool)))


def _observable_oracle_prediction(spec: WorldSpec, target_features: np.ndarray) -> np.ndarray:
    evaluator_spec = WorldSpec(
        world_id=f"evaluator-only-{spec.world_id}",
        merchant_id=f"evaluator-only-{spec.merchant_id}",
        action_family=spec.action_family,
        family=spec.family,
        seed=spec.seed + 4_000_003,
        observations=20_000,
        periods=spec.periods,
    )
    evaluator_observed, evaluator_oracle = generate_world(evaluator_spec)
    model = RandomForestRegressor(
        n_estimators=80,
        max_depth=9,
        min_samples_leaf=40,
        random_state=spec.seed + 719,
        n_jobs=1,
    )
    model.fit(evaluator_observed.features, evaluator_oracle.individual_effect)
    return np.asarray(model.predict(target_features), dtype=float)


def _segment_oracle_value(features: np.ndarray, effect: np.ndarray) -> float:
    segments = (
        np.ones(len(effect), dtype=bool),
        (features[:, 0] > 0.7) & (features[:, 3] > 0.3),
        features[:, 3] > 0.55,
        features[:, 4] > 0,
        (features[:, 3] + features[:, 4]) > 0.45,
    )
    return max(0.0, *(_policy_value(effect, segment) for segment in segments))


def _rank_metrics(
    prediction: np.ndarray,
    scores: np.ndarray,
    clusters: np.ndarray,
    *,
    seed: int,
) -> tuple[float, float, float, float, float, float]:
    order = np.argsort(np.argsort(prediction))
    rank = (order + 0.5) / len(order)
    rate = float(2 * np.mean((rank - 0.5) * scores))
    top = prediction >= np.quantile(prediction, 0.8)
    autoc = float(np.mean(scores[top]) - np.mean(scores))
    qini = float(np.mean(scores[top]) * np.mean(top) - np.mean(scores) * np.mean(top))
    labels = np.unique(clusters)
    rng = np.random.default_rng(seed)
    draws: list[tuple[float, float, float]] = []
    for _ in range(199):
        sampled = rng.choice(labels, size=len(labels), replace=True)
        index = np.concatenate([np.flatnonzero(clusters == label) for label in sampled])
        sampled_prediction = prediction[index]
        sampled_scores = scores[index]
        sampled_order = np.argsort(np.argsort(sampled_prediction))
        sampled_rank = (sampled_order + 0.5) / len(sampled_order)
        sampled_top = sampled_prediction >= np.quantile(sampled_prediction, 0.8)
        draws.append(
            (
                float(2 * np.mean((sampled_rank - 0.5) * sampled_scores)),
                float(np.mean(sampled_scores[sampled_top]) - np.mean(sampled_scores)),
                float(
                    np.mean(sampled_scores[sampled_top]) * np.mean(sampled_top)
                    - np.mean(sampled_scores) * np.mean(sampled_top)
                ),
            )
        )
    array = np.asarray(draws)
    return (
        rate,
        float(np.quantile(array[:, 0], 0.05)),
        autoc,
        float(np.quantile(array[:, 1], 0.05)),
        qini,
        float(np.quantile(array[:, 2], 0.05)),
    )


def decompose(spec: WorldSpec, frozen_result: dict[str, object]) -> DecompositionRow:
    observed, oracle = generate_world(spec)
    n = len(observed.outcome)
    base_end, gate_end = int(0.4 * n), int(0.65 * n)
    base = np.arange(base_end)
    test = np.arange(gate_end, n)
    base = base[observed.observed[base]]
    test = test[observed.observed[test]]
    effect = oracle.individual_effect[test]
    features = observed.features[test]
    best_static = max(0.0, float(np.mean(effect)))
    full_policy = effect > 0
    full_value = _policy_value(effect, full_policy)

    observable_prediction = _observable_oracle_prediction(spec, features)
    observable_policy = observable_prediction > 0
    observable_value = _policy_value(effect, observable_policy)
    segment_value = _segment_oracle_value(features, effect)

    model = UpliftModel(FROZEN_MODEL, spec.seed).fit(
        observed.features[base], observed.treatment[base], observed.outcome[base]
    )
    forest_prediction = model.effect(features)
    promoted = bool(frozen_result["personalization_supported"])
    forest_policy = forest_prediction > 0 if promoted else np.ones(len(test), dtype=bool)
    forest_value = _policy_value(effect, forest_policy)
    forest_increment = forest_value - best_static
    full_increment = full_value - best_static
    observable_increment = observable_value - best_static
    segment_increment = segment_value - best_static
    if observable_increment > MATERIALITY_CP_PER_ELIGIBLE_CUSTOMER:
        classification = (
            "MATERIAL_OBSERVABLE_PERSONALIZATION"
            if promoted and forest_increment > 0
            else "ESTIMATION_OR_POLICY_FAILURE"
        )
    elif full_increment > MATERIALITY_CP_PER_ELIGIBLE_CUSTOMER:
        classification = "MATERIAL_UNOBSERVABLE_PERSONALIZATION"
    else:
        classification = "NONMATERIAL_PERSONALIZATION"

    p = observed.logged_propensity[test]
    scores = _dr_scores(
        model,
        features,
        observed.treatment[test],
        observed.outcome[test],
        p,
    )
    rate, rate_lower, autoc, autoc_lower, qini, qini_lower = _rank_metrics(
        forest_prediction, scores, observed.cluster[test], seed=spec.seed + 991
    )
    weights = np.where(observed.treatment[test], 1 / p, 1 / (1 - p))
    ess = float(np.sum(weights) ** 2 / np.sum(weights**2))
    relevant = np.abs(effect - float(np.mean(effect))) >= MATERIALITY_CP_PER_ELIGIBLE_CUSTOMER
    relevant_variance = float(np.var(effect[relevant])) if np.any(relevant) else 0.0
    target = forest_policy
    reasons = [
        "PERSONALIZATION_PROMOTED" if promoted else "PERSONALIZATION_NOT_SUPPORTED",
        f"V7_SELECTED_POLICY={frozen_result['selected_policy']}",
        f"CLASS={classification}",
    ]
    if observable_increment <= MATERIALITY_CP_PER_ELIGIBLE_CUSTOMER:
        reasons.append("OBSERVABLE_INCREMENT_BELOW_MATERIALITY")
    if forest_increment <= 0:
        reasons.append("FOREST_DID_NOT_BEAT_BEST_STATIC_IN_ORACLE_EVALUATION")
    return DecompositionRow(
        spec.world_id,
        spec.family.value,
        classification,
        full_increment,
        observable_increment,
        segment_increment,
        forest_increment,
        forest_value / full_value if full_value > 0 else 1.0,
        observable_value / full_value if full_value > 0 else 1.0,
        forest_increment / observable_increment if observable_increment > 0 else 0.0,
        float(np.var(effect)),
        relevant_variance,
        float(np.mean(effect > 0)),
        float(np.mean(effect[target])) if np.any(target) else 0.0,
        0.0,
        0.0,
        len(test),
        ess,
        float(np.min(p)),
        float(np.max(p)),
        rate,
        rate_lower,
        autoc,
        autoc_lower,
        qini,
        qini_lower,
        promoted,
        tuple(reasons),
    )


def run() -> dict[str, object]:
    results: dict[str, dict[str, object]] = {}
    for stage in ("development", "validation"):
        document = json.loads(
            (V7_ROOT / "results" / f"{stage}_results.json").read_text()
        )
        results.update({str(row["world_id"]): row for row in document["worlds"]})
    rows = [
        decompose(spec, results[spec.world_id])
        for pack in "HIJKLM"
        for spec in pack_specs(pack)
        if spec.family in HETEROGENEOUS_FAMILIES
    ]
    counts = {
        classification: sum(row.classification == classification for row in rows)
        for classification in (
            "MATERIAL_OBSERVABLE_PERSONALIZATION",
            "NONMATERIAL_PERSONALIZATION",
            "MATERIAL_UNOBSERVABLE_PERSONALIZATION",
            "ESTIMATION_OR_POLICY_FAILURE",
        )
    }
    payload: dict[str, object] = {
        "v7_commit": "aabda4537542c6aebcb3269c96e1b4e684ed5e59",
        "packs": ["H", "I", "J", "K", "L", "M"],
        "consumed_diagnostic_only": True,
        "materiality_cp_per_eligible_customer": MATERIALITY_CP_PER_ELIGIBLE_CUSTOMER,
        "treatment_cost": 0.0,
        "switching_cost": 0.0,
        "cost_note": "V7 DGP encoded net effects and had no separate action/switching cost.",
        "classification_counts": counts,
        "rows": [asdict(row) for row in rows],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    REPORT.write_text(_markdown(payload, rows))
    return payload


def _markdown(payload: dict[str, object], rows: list[DecompositionRow]) -> str:
    lines = [
        "# V7 heterogeneity failure decomposition",
        "",
        "H-M are consumed diagnostic-only packs. This report does not rehabilitate V7 and cannot "
        "be used as V7.1 validation.",
        "",
        "## Frozen economic materiality",
        "",
        (
            "Minimum economically relevant personalization increment: "
            f"**{MATERIALITY_CP_PER_ELIGIBLE_CUSTOMER:.2f} net CP per eligible customer**. "
            "This is inherited from V7's preregistered minimum population effect, not selected "
            "from these results. V7 had no separate treatment or switching-cost fields; both "
            "are therefore reported as zero rather than retrofitted."
        ),
        "",
        "## Classification counts",
        "",
    ]
    counts = cast(dict[str, Any], payload["classification_counts"])
    for name, count in counts.items():
        lines.append(f"- {name}: {count}")
    lines.extend(
        [
            "",
            "## World-level decomposition",
            "",
            (
                "| World | Class | Full oracle Δ | Observable oracle Δ | Segment oracle Δ | "
                "Forest Δ | Forest/observable Δ | Positive subgroup | RATE [lower] | Promoted |"
            ),
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.world_id} | {row.classification} | {row.full_oracle_increment:.4f} | "
            f"{row.observable_oracle_increment:.4f} | {row.segment_oracle_increment:.4f} | "
            f"{row.frozen_forest_increment:.4f} | "
            f"{row.forest_capture_of_observable_increment:.3f} | "
            f"{row.positive_subgroup_prevalence:.1%} | {row.rate:.4f} [{row.rate_lower:.4f}] | "
            f"{'yes' if row.personalization_promoted else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "`FULL_ORACLE` uses individual truth only after policy predictions are frozen. "
            "`OBSERVABLE_ORACLE` is a separately fitted evaluator-only forest trained on 20,000 "
            "independent synthetic rows using legitimate pre-treatment features and oracle labels; "
            "it shares no fitted state or predictions with the policy. `SEGMENT_ORACLE` can choose "
            "only from the fixed RFM/intent/loyalty segment set.",
            "",
            "The old aggregate 80% gate is withdrawn. V7.1 success is conditional on whether "
            "material economic personalization is observable in the first place.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
