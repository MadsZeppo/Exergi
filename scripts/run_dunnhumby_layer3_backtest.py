from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import numpy as np
import pandas as pd

from commercial_twin.customer_twin_core import (
    ActionDefinition,
    ActionFamily,
    EvidenceBoundAnswerRenderer,
    EvidenceType,
    action_evidence_for_dataset,
    srm_check,
)
from decision_engine.causal.dunnhumby_backtest import (
    build_pre_exposure_frame,
    campaign_metadata,
    campaign_support,
    deterministic_aa,
    evaluate_frozen,
    fit_and_freeze,
    preregistered_split,
    reveal_outcome,
)
from decision_engine.ledger.store import PredictionLedger

PROCESSED = Path("data/processed/dunnhumby/complete-journey")
OUTPUT = Path("artifacts/layer3_validation/dunnhumby")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    descriptions, transaction_min, transaction_max = campaign_metadata(PROCESSED)
    cutoff, development_campaigns, backtest_campaigns = preregistered_split(
        descriptions, transaction_min, transaction_max
    )
    if development_campaigns.empty or backtest_campaigns.empty:
        raise ValueError("preregistered chronological split has no eligible campaigns")
    support = campaign_support(
        PROCESSED, [str(value) for value in backtest_campaigns["campaign_id"]]
    )
    selected_campaign = str(support.iloc[0]["campaign_id"])
    selected_start = pd.Timestamp(
        backtest_campaigns.loc[
            backtest_campaigns["campaign_id"].astype(str) == selected_campaign, "start_date"
        ].iloc[0]
    ).to_pydatetime()

    development_rows: list[pd.DataFrame] = []
    development_outcomes: list[np.ndarray] = []
    for row in development_campaigns.itertuples(index=False):
        campaign_id = str(row.campaign_id)
        start = pd.Timestamp(row.start_date).to_pydatetime()
        frame = build_pre_exposure_frame(PROCESSED, campaign_id, start)
        outcome = reveal_outcome(PROCESSED, frame["household_id"].astype(str).tolist(), start)
        frame["campaign_id"] = campaign_id
        development_rows.append(frame)
        development_outcomes.append(outcome)
    development = pd.concat(development_rows, ignore_index=True)
    y_development = np.concatenate(development_outcomes)

    # Final frame contains only pre-exposure state and observed assignment; no outcome is loaded.
    final = build_pre_exposure_frame(PROCESSED, selected_campaign, selected_start)
    frozen = fit_and_freeze(
        development,
        y_development,
        final,
        campaign_id=selected_campaign,
        start_date=selected_start,
    )
    action = ActionDefinition(
        action_id=f"dunnhumby-campaign-{selected_campaign}",
        family=ActionFamily.TARGETED_COMMUNICATION,
        parameters={"campaign_id": selected_campaign, "outcome_window_days": 30},
    )
    ledger = PredictionLedger(OUTPUT / "prediction_ledger.duckdb")
    query_id = f"dunnhumby-campaign-{selected_campaign}-30d"
    ledger.append_twin_query(
        query_id=query_id,
        as_of=selected_start.replace(tzinfo=UTC),
        query_plan={
            "intent": "CAUSAL",
            "action": action.model_dump(mode="json"),
            "primary_outcome": "household purchased within 30 days",
            "cutoff": cutoff.isoformat(),
        },
        snapshot_version=f"dunnhumby-cran-1.1.0-{selected_start.date()}",
        model_version="development-fit-aipw-logistic-v1",
        answer_distribution={
            "transported_mean_uplift": float(frozen.predicted_uplift.mean()),
            "propensity_min": float(frozen.propensity.min()),
            "propensity_median": float(np.median(frozen.propensity)),
            "propensity_max": float(frozen.propensity.max()),
        },
        evidence_type=EvidenceType.CAUSAL_OBSERVATIONAL.value,
        validation_status="FROZEN_BEFORE_BACKTEST_OUTCOME_REVEAL",
        action=action.model_dump(mode="json"),
        predicted_incremental_effect={
            "purchase_probability": float(frozen.predicted_uplift.mean())
        },
        economic_estimate={"status": "NOT_COMPUTABLE_MISSING_COST_FIELDS"},
        decision_state="INTERNAL_BACKTEST_PENDING",
    )
    (OUTPUT / "frozen_prediction.json").write_text(
        json.dumps(
            {
                "query_id": query_id,
                "campaign_id": selected_campaign,
                "start_date": selected_start.isoformat(),
                "cutoff": cutoff.isoformat(),
                "predicted_uplift": float(frozen.predicted_uplift.mean()),
                "outcomes_loaded": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Reveal boundary: this is the first final-outcome query.
    outcome = reveal_outcome(PROCESSED, final["household_id"].astype(str).tolist(), selected_start)
    realized = evaluate_frozen(frozen, outcome)
    aa = deterministic_aa(
        final["household_id"].astype(str).tolist(), outcome, final["treatment"].to_numpy(int)
    )
    aa_srm = srm_check(int(aa["arm_one"]), int(aa["arm_zero"]), 0.5)
    diagnostic_gates = {
        "treated_ess": frozen.treated_ess >= 200,
        "control_ess": frozen.control_ess >= 200,
        "overlap": frozen.overlap_fraction >= 0.80,
        "srm": bool(aa_srm["trusted"]),
        "aa": float(aa["p_value"]) >= 0.05,
        "frozen_before_reveal": True,
        "naive_and_adjusted_reported": True,
    }
    diagnostic_supported = all(diagnostic_gates.values())
    scientific_gates = {**diagnostic_gates, "untouched_final_implementation": False}
    evidence = action_evidence_for_dataset(
        "Dunnhumby Complete Journey",
        action,
        assignment_observed=True,
        overlap_valid=(
            diagnostic_gates["overlap"]
            and diagnostic_gates["treated_ess"]
            and diagnostic_gates["control_ess"]
        ),
        frozen_backtest_available=False,
    )
    if evidence.evidence_type != EvidenceType.INSUFFICIENT:
        raise AssertionError("failed scientific gate did not downgrade evidence")
    ledger.append_twin_query_outcome(
        query_id,
        realized_outcome={
            "adjusted_ate": realized["adjusted_ate"],
            "naive_ate": realized["naive_ate"],
            "outcome_rate": float(outcome.mean()),
        },
        calibration_update={
            "transport_error": float(realized["adjusted_ate"])
            - float(frozen.predicted_uplift.mean()),
            "uplift_calibration": realized["uplift_calibration"],
        },
    )
    ledger.close()
    renderer = EvidenceBoundAnswerRenderer()
    summary = {
        "label": "REAL OBSERVATIONAL ASSIGNMENT — NOT RANDOMIZED",
        "source_scope": "CC0 CRAN completejourney 1.1.0 one-year universe",
        "preregistered_cutoff": cutoff.isoformat(),
        "development_campaigns": int(len(development_campaigns)),
        "backtest_campaigns": int(len(backtest_campaigns)),
        "selected_campaign": selected_campaign,
        "selected_campaign_start": selected_start.isoformat(),
        "selection_basis": "largest qualified treated support without post-exposure outcomes",
        "households": int(len(final)),
        "treated": int(final["treatment"].sum()),
        "control": int((1 - final["treatment"]).sum()),
        "predicted_transport_uplift": float(frozen.predicted_uplift.mean()),
        "realized": realized,
        "propensity": {
            "min": float(frozen.propensity.min()),
            "median": float(np.median(frozen.propensity)),
            "max": float(frozen.propensity.max()),
            "fraction_clipped": frozen.fraction_clipped,
            "overlap_fraction": frozen.overlap_fraction,
        },
        "ess": {"treated": frozen.treated_ess, "control": frozen.control_ess},
        "balance": {
            "max_absolute_smd_before": frozen.max_smd_before,
            "max_absolute_smd_after": frozen.max_smd_after,
        },
        "aa": {**aa, "srm": aa_srm},
        "diagnostic_gates": diagnostic_gates,
        "scientific_gates": scientific_gates,
        "evidence": evidence.model_dump(mode="json"),
        "rendered_answer": renderer.render_statement(
            evidence.evidence_type,
            f"campaign {selected_campaign} changed 30-day purchase probability by "
            f"{float(realized['adjusted_ate']):.3f}",
        ),
        "profit_status": "NOT_COMPUTABLE_MISSING_COST_FIELDS",
        "diagnostic_verdict": (
            "SUPPORTED_WITH_ASSUMPTIONS" if diagnostic_supported else "INSUFFICIENT"
        ),
        "verdict": "INSUFFICIENT",
        "final_validation_status": (
            "BURNED_AFTER_INVALID_FIRST_PROPENSITY_IMPLEMENTATION; CORRECTED_DIAGNOSTIC_ONLY"
        ),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
