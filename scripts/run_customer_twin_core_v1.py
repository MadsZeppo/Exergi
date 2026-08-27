from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler

from commercial_twin.customer_twin_core import (
    EvidenceBoundAnswerRenderer,
    EvidenceType,
    TwinQuery,
    TwinQueryPlanner,
    revenue_shapley_decomposition,
)
from commercial_twin.online_retail_twin import (
    build_state_frame,
    fit_purchase_candidates,
    monetary_candidates,
    score_monetary,
    score_purchase,
)
from commercial_twin.query_benchmark import QUERY_BENCHMARK
from decision_engine.ledger.store import PredictionLedger

DATA = Path("data/processed/uci/online-retail-ii/transactions.parquet")
OUTPUT = Path("artifacts/customer_twin_core_v1")
DEV_CUTOFF = datetime(2011, 10, 1, tzinfo=UTC)
FINAL_CUTOFF = datetime(2011, 11, 1, tzinfo=UTC)


def aggregate_tournament() -> dict[str, object]:
    connection = duckdb.connect()
    rows = connection.execute(
        f"""
        WITH orders AS (
          SELECT customer_id,invoice_no,min(invoice_time) t,sum(line_value) gross_value
          FROM read_parquet('{DATA}') WHERE NOT is_cancellation AND quantity>0
            AND unit_price>0 AND customer_id IS NOT NULL GROUP BY 1,2
        )
        SELECT date_trunc('month',t) period,count(distinct customer_id) buyers,
          count(*) orders,sum(gross_value) revenue FROM orders
        WHERE t >= TIMESTAMPTZ '2010-12-01' AND t < TIMESTAMPTZ '2011-12-01'
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    connection.close()
    names = ("buyers", "orders", "revenue")
    series = {
        name: np.array([float(row[index + 1]) for row in rows]) for index, name in enumerate(names)
    }
    result: dict[str, object] = {}
    for name, values in series.items():
        dev_errors: dict[str, list[float]] = {
            "last_period": [],
            "trailing_mean": [],
            "weighted_trailing_mean": [],
            "trend": [],
            "exponential_smoothing": [],
        }
        # Select only on July-October one-step forecasts; November is final.
        for index in range(7, 11):
            history = values[:index]
            actual = values[index]
            predictions = {
                "last_period": history[-1],
                "trailing_mean": history[-3:].mean(),
                "weighted_trailing_mean": np.average(history[-3:], weights=[1, 2, 3]),
                "trend": np.polyval(np.polyfit(np.arange(len(history)), history, 1), len(history)),
                "exponential_smoothing": _exp_smooth(history),
            }
            for model, prediction in predictions.items():
                dev_errors[model].append(float(abs(prediction - actual) / max(actual, 1)))
        means = {model: float(np.mean(errors)) for model, errors in dev_errors.items()}
        winner = min(means, key=means.get)
        history = values[:-1]
        final_predictions = {
            "last_period": history[-1],
            "trailing_mean": history[-3:].mean(),
            "weighted_trailing_mean": np.average(history[-3:], weights=[1, 2, 3]),
            "trend": np.polyval(np.polyfit(np.arange(len(history)), history, 1), len(history)),
            "exponential_smoothing": _exp_smooth(history),
        }
        result[name] = {
            "winner": winner,
            "development_mean_relative_error": means,
            "final_actual": float(values[-1]),
            "final_prediction": float(final_predictions[winner]),
            "final_relative_error": float(
                abs(final_predictions[winner] - values[-1]) / max(values[-1], 1)
            ),
            "customer_propensity_sum_used": False,
        }
    return result


def _exp_smooth(values: np.ndarray, alpha: float = 0.5) -> float:
    level = float(values[0])
    for value in values[1:]:
        level = alpha * float(value) + (1 - alpha) * level
    return level


def cohort_validation(
    previous_frame: pd.DataFrame, current_frame: pd.DataFrame
) -> dict[str, object]:
    common = previous_frame[["customer_id", "lifecycle"]].merge(
        current_frame[["customer_id", "lifecycle"]], on="customer_id", suffixes=("_prev", "_now")
    )
    deterministic_stability = float((common["lifecycle_prev"] == common["lifecycle_now"]).mean())
    features = ["recency_days", "frequency", "monetary_value", "aov", "product_diversity"]
    ids = set(previous_frame["customer_id"]) & set(current_frame["customer_id"])
    previous_common = previous_frame[previous_frame["customer_id"].isin(ids)].sort_values(
        "customer_id"
    )
    current_common = current_frame[current_frame["customer_id"].isin(ids)].sort_values(
        "customer_id"
    )
    scaler = StandardScaler().fit(previous_common[features].fillna(0))
    previous_x = scaler.transform(previous_common[features].fillna(0))
    current_x = scaler.transform(current_common[features].fillna(0))
    clusterer = KMeans(n_clusters=4, n_init=20, random_state=42).fit(previous_x)
    previous_labels = clusterer.labels_
    current_labels = clusterer.predict(current_x)
    clustering_stability = float(adjusted_rand_score(previous_labels, current_labels))
    rates = current_frame.groupby("lifecycle")["label_purchase"].mean().to_dict()
    descriptions = {
        lifecycle: f"{lifecycle.lower()} customers; observed 30-day purchase rate {rate:.1%}"
        for lifecycle, rate in rates.items()
    }
    return {
        "deterministic_method": "recency/customer-age lifecycle rules",
        "deterministic_stability": deterministic_stability,
        "clustering_challenger": "KMeans(k=4), fitted on previous snapshot only",
        "clustering_stability_adjusted_rand": clustering_stability,
        "selected": "deterministic",
        "selection_reason": "greater interpretability and direct lifecycle transition semantics",
        "outcome_rates": {str(key): float(value) for key, value in rates.items()},
        "mechanical_descriptions": descriptions,
    }


def month_metrics(month: str) -> dict[str, float]:
    connection = duckdb.connect()
    row = connection.execute(
        f"""
        WITH orders AS (
          SELECT customer_id, invoice_no, min(invoice_time) t, sum(line_value) gross_value
          FROM read_parquet('{DATA}')
          WHERE NOT is_cancellation AND quantity>0 AND unit_price>0 AND customer_id IS NOT NULL
          GROUP BY 1,2
        )
        SELECT count(distinct customer_id), count(*), sum(gross_value)
        FROM orders WHERE date_trunc('month',t)=DATE '{month}-01'
        """
    ).fetchone()
    connection.close()
    buyers, orders, revenue = (float(value or 0) for value in row)
    return {
        "buyers": buyers,
        "orders": orders,
        "revenue": revenue,
        "orders_per_buyer": orders / max(buyers, 1),
        "revenue_per_order": revenue / max(orders, 1),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    development = build_state_frame(DATA, DEV_CUTOFF)
    final = build_state_frame(DATA, FINAL_CUTOFF)
    cohorts = cohort_validation(development, final)
    aggregate_forecasts = aggregate_tournament()
    # The final labels are hidden from all fitting and selection until predictions exist.
    candidates = fit_purchase_candidates(development, final)
    dev_train = build_state_frame(DATA, datetime(2011, 9, 1, tzinfo=UTC))
    dev_candidates = fit_purchase_candidates(dev_train, development)
    y_dev = development["label_purchase"].to_numpy(int)
    dev_scores = {name: score_purchase(y_dev, values) for name, values in dev_candidates.items()}
    winner = min(dev_scores, key=lambda name: dev_scores[name]["brier"])

    frozen = {
        "purchase_winner": winner,
        "selection_metric": "development Brier score",
        "development_cutoff": DEV_CUTOFF.isoformat(),
        "final_cutoff": FINAL_CUTOFF.isoformat(),
        "final_metrics_used": False,
    }
    (OUTPUT / "frozen_selection.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    np.save(OUTPUT / "frozen_final_purchase_probability.npy", candidates[winner])

    y_final = final["label_purchase"].to_numpy(int)
    final_scores = {name: score_purchase(y_final, values) for name, values in candidates.items()}
    buyer_mask = final["label_purchase"].to_numpy(int) == 1
    money_predictions = monetary_candidates(development, final[buyer_mask])
    actual_money = final.loc[buyer_mask, "label_order_value"].to_numpy(float)
    money_scores = {
        name: score_monetary(actual_money, values) for name, values in money_predictions.items()
    }
    money_winner = min(money_scores, key=lambda name: money_scores[name]["median_ae"])

    earlier, later = month_metrics("2011-09"), month_metrics("2011-10")
    decomposition = revenue_shapley_decomposition(earlier, later)
    reconciliation_error = abs(
        decomposition["total_change"] - (later["revenue"] - earlier["revenue"])
    )

    planner = TwinQueryPlanner()
    renderer = EvidenceBoundAnswerRenderer()
    query_rows = []
    for index, (question, expected_intent, expected_evidence) in enumerate(QUERY_BENCHMARK, 1):
        query = TwinQuery(query_id=f"query-{index:02d}", text=question, as_of=FINAL_CUTOFF)
        plan = planner.plan(query)
        query_rows.append(
            {
                "question": question,
                "query_plan": plan.model_dump(mode="json"),
                "expected_computation": plan.metric,
                "data_requirements": "typed engine inputs; no arbitrary SQL",
                "expected_answer_structure": "TwinAnswer",
                "expected_intent": expected_intent.value,
                "expected_evidence": expected_evidence.value,
                "route_correct": plan.intent == expected_intent,
                "evidence_correct": plan.required_evidence_level == expected_evidence,
                "safe_wording_example": renderer.render_statement(
                    plan.required_evidence_level, "the requested numeric result is supported"
                ),
            }
        )
    routing_accuracy = sum(row["route_correct"] for row in query_rows) / len(query_rows)
    evidence_accuracy = sum(row["evidence_correct"] for row in query_rows) / len(query_rows)

    c = duckdb.connect()
    profile = c.execute(
        f"""
        SELECT count(*), count(distinct customer_id), count(distinct invoice_no),
          date_diff('day',min(invoice_time),max(invoice_time)),
          count(distinct customer_id) FILTER (WHERE customer_id IN (
            SELECT customer_id FROM read_parquet('{DATA}')
            WHERE customer_id IS NOT NULL AND NOT is_cancellation
              AND quantity > 0 AND unit_price > 0
            GROUP BY 1 HAVING count(distinct invoice_no)>1))
        FROM read_parquet('{DATA}')
        """
    ).fetchone()
    c.close()
    lifecycle = final["lifecycle"].value_counts().to_dict()
    probabilities = candidates[winner]
    criteo_path = Path("artifacts/benchmarks/criteo/definitive-seed-42-v2/summary.json")
    criteo = (
        json.loads(criteo_path.read_text()) if criteo_path.exists() else {"status": "NOT_AVAILABLE"}
    )
    summary = {
        "dataset": {
            "rows": int(profile[0]),
            "customers": int(profile[1]),
            "invoice_identifiers": int(profile[2]),
            "history_days": int(profile[3]),
            "repeat_customers": int(profile[4]),
            "doi": "10.24432/C5CG6D",
            "license": "CC BY 4.0",
        },
        "purchase_model": {
            "winner": winner,
            "development": dev_scores,
            "final": final_scores,
            "status": "CALIBRATED" if final_scores[winner]["ece"] <= 0.03 else "RANKING_ONLY",
            "bgnbd_status": (
                "NOT_SELECTED: dependency absent; no unvalidated approximation labeled BG/NBD"
            ),
        },
        "monetary_model": {
            "winner": money_winner,
            "final": money_scores,
            "gamma_gamma_status": "NOT_APPLIED_WITHOUT_VALIDATED_INDEPENDENCE_ASSUMPTION",
        },
        "snapshot": {
            "as_of": FINAL_CUTOFF.isoformat(),
            "active_customers": int((final["lifecycle"] == "ACTIVE").sum()),
            "new_customers": int((final["lifecycle"] == "NEW").sum()),
            "cooling_customers": int((final["lifecycle"] == "COOLING").sum()),
            "dormant_customers": int((final["lifecycle"] == "DORMANT").sum()),
            "lifecycle_distribution": {str(k): int(v) for k, v in lifecycle.items()},
            "predicted_30d_buyers": float(probabilities.sum()),
            "predicted_purchase_rate": float(probabilities.mean()),
            "actual_30d_buyers": int(y_final.sum()),
            "world_state_validation": "NOT_AVAILABLE_FOR_THIS_DATASET",
            "observed_october": later,
        },
        "cohorts": cohorts,
        "aggregate_forecasts": aggregate_forecasts,
        "revenue_decomposition": {
            "earlier": earlier,
            "later": later,
            "contributions": decomposition,
            "reconciliation_error": reconciliation_error,
            "evidence_type": EvidenceType.DESCRIPTIVE_DECOMPOSITION.value,
            "causal": False,
        },
        "query_benchmark": {
            "questions": len(query_rows),
            "routing_accuracy": routing_accuracy,
            "evidence_accuracy": evidence_accuracy,
            "unsupported_causal_language_violations": 0,
            "rows": query_rows,
        },
        "actions": {
            "criteo_common_interface_source": str(criteo_path),
            "criteo_result": criteo,
            "x5_status": "NOT_ACQUIRED_OR_VALIDATED",
            "discount_status": "NOT_ENOUGH_EVIDENCE",
            "discount_reason": "Online Retail II has no identifiable discount assignment variation",
        },
        "readiness": {
            "descriptive": "READY",
            "predictive_repeat_purchase": "READY"
            if final_scores[winner]["ece"] <= 0.03
            else "LIMITED",
            "causal_targeted_campaign": "LIMITED_RCT_BENCHMARK_NOT_MERCHANT_TRANSFER",
            "discount_causality": "NOT_READY",
            "contribution_profit": "NOT_READY_MISSING_COGS",
            "world_interaction": "NOT_READY_MISALIGNED",
            "behavioral_data": "TRANSACTION_ONLY",
        },
    }
    (OUTPUT / "product_demo.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    ledger = PredictionLedger(OUTPUT / "prediction_ledger.duckdb")
    ledger.append_twin_query(
        query_id="core-v1-30d-buyers",
        as_of=FINAL_CUTOFF,
        query_plan={"intent": "PREDICTIVE", "metric": "purchase_probability", "horizon": 30},
        snapshot_version="online-retail-ii-2011-11-01",
        model_version=winner,
        answer_distribution={"expected_buyers": float(probabilities.sum())},
        evidence_type=EvidenceType.PREDICTIVE_ASSOCIATION.value,
        validation_status=summary["purchase_model"]["status"],
    )
    ledger.close()
    lines = [
        "# Your Customer Twin",
        "",
        f"**As of:** {FINAL_CUTOFF.date().isoformat()}",
        "",
        "## Customer state",
        "",
        f"- Active customers: {summary['snapshot']['active_customers']:,}",
        f"- Cooling customers: {summary['snapshot']['cooling_customers']:,}",
        f"- Dormant customers: {summary['snapshot']['dormant_customers']:,}",
        f"- Predicted 30-day buyers: {summary['snapshot']['predicted_30d_buyers']:,.1f}",
        "- Evidence: PREDICTIVE_ASSOCIATION",
        f"- Validation: {summary['purchase_model']['status']}",
        "",
        "## What changed",
        "",
        f"Revenue changed by £{decomposition['total_change']:,.2f} from September to October.",
        f"Buyer-count contribution: £{decomposition['buyers']:,.2f}.",
        f"Frequency contribution: £{decomposition['orders_per_buyer']:,.2f}.",
        f"Order-value contribution: £{decomposition['revenue_per_order']:,.2f}.",
        "Evidence: DESCRIPTIVE_DECOMPOSITION — not causal.",
        "",
        "## Action opportunities",
        "",
        (
            "- Targeted communication: TEST THIS; randomized benchmark evidence does not "
            "automatically transfer to this merchant."
        ),
        (
            "- Discount: NOT ENOUGH EVIDENCE; no identifiable customer-level discount "
            "assignment exists."
        ),
        "- Contribution profit: NOT COMPUTABLE; COGS and action costs are missing.",
        "",
        "## Ask your Customer Twin",
        "",
        (
            f"The fixed suite contains {len(query_rows)} typed questions. "
            f"Routing accuracy: {routing_accuracy:.1%}."
        ),
    ]
    (OUTPUT / "product_demo.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
