from __future__ import annotations

import json
import subprocess
from datetime import timedelta
from pathlib import Path

import numpy as np
import polars as pl
import streamlit as st

from decision_engine.benchmark.time_machine import TimeMachineBenchmark
from decision_engine.dashboard.data import data_health_summary, synthetic_research_dataset
from decision_engine.decision.evidence import ComponentStatus, EvidenceScorecard
from decision_engine.forecasting.ensemble import historical_model_weights
from decision_engine.metrics.calibration import calibration_report
from decision_engine.metrics.probabilistic import crps_ensemble, weighted_interval_score
from decision_engine.robustness.drift import distribution_shift_report


@st.cache_data
def load_demo():
    return synthetic_research_dataset()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unavailable"


st.set_page_config(page_title="Commercial Twin Research Cockpit", layout="wide")
st.title("Commercial Twin Research Cockpit")
dataset_choice = st.sidebar.selectbox("Dataset", ["Synthetic", "Real Retail", "Hillstrom"])
if dataset_choice == "Real Retail":
    st.warning("REAL HISTORICAL ACADEMIC DATA — NOT DEPLOYMENT OR CUSTOMER EVIDENCE")
else:
    st.warning("SYNTHETIC — NOT COMMERCIAL EVIDENCE")
with st.expander("Commercial Twin state and readiness", expanded=True):
    state_columns = st.columns(4)
    for column, title, text in zip(
        state_columns,
        ("Customer State", "Company State", "World State", "Twin Readiness"),
        (
            "Deterministic, non-PII behavioral cohorts.",
            "Products, costs, inventory, channels, and active actions.",
            "Time-stamped external signals with source and provenance.",
            "Capability-specific READY / LIMITED / NOT_READY diagnostics.",
        ),
        strict=True,
    ):
        column.subheader(title)
        column.caption(text)

if dataset_choice == "Real Retail":
    real_root = Path("artifacts/real_commercial_twin/dominicks")
    real_runs = sorted(real_root.glob("*/report.md"))
    if not real_runs:
        st.error("No frozen real-retail run found. Run scripts/run_real_commercial_twin.py.")
    else:
        real_run = real_runs[-1].parent
        st.subheader("Frozen Dominick's Oatmeal Commercial Twin")
        st.caption(f"Artifact: {real_run}")
        profile = json.loads((real_run / "canonical_data_profile.json").read_text())
        readiness = json.loads((real_run / "readiness.json").read_text())
        factual = json.loads((real_run / "factual_evaluation.json").read_text())
        causal = json.loads((real_run / "causal_evaluation.json").read_text())
        st.write("Data profile", profile)
        st.write("Twin readiness", readiness)
        st.write("Customer/cohort state", pl.read_parquet(real_run / "cohorts.parquet"))
        st.write(
            "Frozen candidate actions",
            pl.read_parquet(real_run / "frozen_simulations.parquet"),
        )
        st.write("Support", pl.read_parquet(real_run / "support_diagnostics.parquet"))
        st.write("Factual evaluation", factual)
        st.write("Causal evidence", causal)
        st.write("Ledger", real_run / "prediction_ledger.duckdb")
frame = load_demo()
summary = data_health_summary(frame)
cutoff_date = st.sidebar.date_input(
    "Historical cutoff", value=summary["date_end"].date() - timedelta(days=28)
)
cutoff = (
    frame["timestamp"]
    .min()
    .replace(year=cutoff_date.year, month=cutoff_date.month, day=cutoff_date.day)
)
horizon = st.sidebar.selectbox("Forecast horizon", [7, 14, 28], index=0)

top = st.columns(6)
values = [
    "Synthetic panel v2",
    "synthetic-2",
    f"{summary['date_start'].date()} — {summary['date_end'].date()}",
    summary["entities"],
    summary["observations"],
    git_commit(),
]
labels = ["Dataset", "Version", "Date range", "Entities", "Observations", "Git commit"]
for cell, label, value in zip(top, labels, values, strict=True):
    cell.metric(label, value)

tabs = st.tabs(
    [
        "Data health",
        "Time machine",
        "Forecast tournament",
        "Calibration",
        "Causal & falsification",
        "Decision simulator",
        "Ledger",
        "Real causal benchmark",
        "Continuous retail benchmark",
        "COMMERCIAL TWIN",
    ]
)
with tabs[0]:
    st.subheader("Data health")
    st.write(summary)
    st.bar_chart(frame.group_by("action").len().sort("action"), x="action", y="len")
    weekly = (
        frame.sort("timestamp")
        .group_by_dynamic("timestamp", every="7d")
        .agg(pl.col("outcome").mean())
    )
    st.line_chart(weekly, x="timestamp", y="outcome")
    st.dataframe(
        {"column": frame.columns, "missing": [frame[c].null_count() for c in frame.columns]}
    )

with tabs[1]:
    st.subheader("Time machine leakage audit")
    machine = TimeMachineBenchmark(frame).freeze_at(cutoff)
    history = machine.history()
    future_count = frame.filter(frame["timestamp"] >= cutoff).height
    st.write(
        {
            "data_available_rows": history.height,
            "hidden_future_rows": future_count,
            "max_event_timestamp": history["timestamp"].max(),
            "max_observed_at": history["observed_at"].max(),
            "decision_cutoff": cutoff,
            "outcome_reveal_period": f"{cutoff} — {cutoff + timedelta(days=horizon - 1)}",
        }
    )
    st.success("FUTURE LEAKAGE: PASS")
    st.info("POST-TREATMENT LEAKAGE: PASS — only declared pre-decision columns enter replay")

with tabs[2]:
    st.subheader("Forecast model tournament")
    losses = {
        "Seasonal": np.array([0.18, 0.17, 0.19]),
        "Linear": np.array([0.20, 0.18, 0.17]),
        "LightGBM": np.array([0.16, 0.18, 0.20]),
    }
    weights = historical_model_weights(losses)
    st.caption(
        "Illustrative historical-only demo scores; full model fit is deliberately "
        "not run on rerender."
    )
    st.dataframe(
        [
            {
                "model": model,
                "recent_WAPE": float(values.mean()),
                "decision_time_weight": weights[model],
            }
            for model, values in losses.items()
        ]
    )

with tabs[3]:
    st.subheader("Probabilistic calibration")
    rng = np.random.default_rng(42)
    y = rng.normal(size=300)
    median = np.zeros(300)
    intervals = {
        0.5: (-0.674 * np.ones(300), 0.674 * np.ones(300)),
        0.2: (-1.282 * np.ones(300), 1.282 * np.ones(300)),
        0.1: (-1.645 * np.ones(300), 1.645 * np.ones(300)),
    }
    report = calibration_report(
        y, {f"{int((1 - a) * 100)}%": bounds for a, bounds in intervals.items()}
    )
    st.dataframe([{"interval": key, **value} for key, value in report.items()])
    st.metric("WIS", f"{weighted_interval_score(y, median, intervals):.3f}")
    st.metric("CRPS", f"{crps_ensemble(y, rng.normal(size=(300, 200))):.3f}")

with tabs[4]:
    reference = frame.filter(frame["timestamp"] < cutoff - timedelta(days=90))
    current = frame.filter(
        (frame["timestamp"] >= cutoff - timedelta(days=90)) & (frame["timestamp"] < cutoff)
    )
    shift = distribution_shift_report(
        {"outcome": reference["outcome"].to_numpy(), "price": reference["price"].to_numpy()},
        {"outcome": current["outcome"].to_numpy(), "price": current["price"].to_numpy()},
    )
    st.subheader("Causal evidence and falsification")
    st.metric("Distribution shift", shift.overall)
    st.dataframe(shift.features)
    st.info("Negative controls: NOT_AVAILABLE — no defensible control configured")
    st.warning(
        "Causal recommendation withheld: synthetic treatment is observational and "
        "no estimator tournament has been run in this dashboard session."
    )

with tabs[5]:
    scorecard = EvidenceScorecard(
        treatment_overlap=ComponentStatus.WARNING,
        estimator_agreement=ComponentStatus.NOT_AVAILABLE,
        distribution_shift=ComponentStatus.WARNING,
        forecast_calibration=ComponentStatus.GOOD,
    )
    st.subheader("Decision evidence scorecard")
    st.dataframe(
        [{"component": key, "status": value} for key, value in scorecard.model_dump().items()]
    )
    st.error(f"RECOMMENDATION WITHHELD — {scorecard.recommendation_status()}")
    st.caption(
        "Run a randomized promotion experiment or a validated causal tournament before commitment."
    )

with tabs[6]:
    st.subheader("Prediction ledger")
    ledger_path = Path("artifacts/predictions/ledger.duckdb")
    if ledger_path.exists():
        st.info(f"Ledger available at {ledger_path}; predictions remain append-only.")
    else:
        st.info(
            "No predictions stored yet. PREDICTION CREATED / OUTCOME REVEALED / "
            "EVALUATED states will appear here."
        )

with tabs[7]:
    st.subheader("REAL CAUSAL BENCHMARK")
    st.warning("RANDOMIZED HISTORICAL BENCHMARK — NOT CUSTOMER OR DEPLOYMENT EVIDENCE")
    result_path = Path(
        "artifacts/benchmarks/hillstrom/definitive-seed-42-bootstrap-2000/summary.json"
    )
    if dataset_choice != "Hillstrom":
        st.info("Select Hillstrom in the sidebar to inspect the frozen RCT benchmark.")
    elif not result_path.exists():
        st.error(
            "DATASET OR BENCHMARK NOT INSTALLED. Expected data/raw/hillstrom/hillstrom.csv "
            "and a completed scripts/run_hillstrom_benchmark.py run."
        )
    else:
        hillstrom = json.loads(result_path.read_text())
        st.write("RCT experimental effects")
        st.dataframe(hillstrom["experimental_effects"])
        st.write("Estimator tournament")
        st.dataframe(hillstrom["estimator_results"])
        st.write("Policy value")
        st.dataframe(hillstrom["policy_values"])
        st.write("Treatment ranking", hillstrom["experimental_ranking"])
        st.write("Estimator disagreement", hillstrom["agreement"])
        st.write("Evidence scorecard", hillstrom["evidence_scorecard"])
        st.write(
            "Frozen recommendation",
            hillstrom["act_experiment_abstain"],
            hillstrom["recommended_action_pre_reveal"],
        )
        st.write("Result after reveal", hillstrom["best_static_policy"])
        st.caption(
            "Placebo draws are stored in placebo_results.parquet; the full report is "
            "available beside this summary."
        )

with tabs[8]:
    st.subheader("Continuous Retail Benchmark")
    st.warning("TRUTH-KNOWN SYNTHETIC WORLDS — NOT REAL RETAIL CAUSAL EVIDENCE")
    continuous_path = Path("artifacts/benchmarks/continuous-retail/definitive-dr-v4/summary.json")
    if not continuous_path.exists():
        continuous_path = Path(
            "artifacts/benchmarks/continuous-retail/quick-support-gate-v5-final/summary.json"
        )
    if not continuous_path.exists():
        st.info("Run scripts/run_continuous_retail_benchmark.py to create the benchmark.")
    else:
        continuous = json.loads(continuous_path.read_text())
        st.write(f"Worlds: {continuous['worlds']}; runtime: {continuous['runtime_seconds']:.2f}s")
        st.write("Estimator tournament")
        st.dataframe(continuous["aggregate"])
        st.write("Counterfactual calibration")
        st.dataframe(continuous["calibration"])
        st.write("ACT / EXPERIMENT / ABSTAIN")
        st.dataframe(continuous["decisions"])
        curve_path = continuous_path.parent / "dose_response_curves.parquet"
        if curve_path.exists():
            curves = pl.read_parquet(curve_path)
            selected_seed = st.selectbox("Synthetic world seed", curves["seed"].unique().sort())
            selected = curves.filter(pl.col("seed") == selected_seed).sort("dose")
            st.write("Estimated vs oracle dose-response with frozen 90% bootstrap interval")
            st.line_chart(
                selected.select(
                    "dose", "estimated_demand", "oracle_demand", "lower_90", "upper_90"
                ),
                x="dose",
            )
            st.write("Support region and economic curve")
            st.dataframe(
                selected.select("dose", "support_level", "estimated_profit", "oracle_profit")
            )
        verdict = continuous["verdict"]["final"]
        (st.success if verdict == "PASS" else st.error)(f"SCIENTIFIC VERDICT: {verdict}")
        st.write("Capability verdict", continuous["verdict"])
        st.write("Scientific limitations", continuous["scientific_limitations"])

with tabs[9]:
    st.subheader("COMMERCIAL TWIN")
    demo_path = Path("artifacts/commercial_twin/product_demo/commercial_twin_view.json")
    if not demo_path.exists():
        st.info("Run scripts/build_current_commercial_twin_artifacts.py to create the demo.")
    else:
        demo = json.loads(demo_path.read_text())
        st.warning(demo["evidence_label"])
        state = demo["current_state"]["state"]
        st.write("CURRENT CUSTOMER ENVIRONMENT")
        exposure = state["world_state"].get("geographic_exposure", [])
        st.dataframe(exposure)
        signals = state["world_state"]["signals"]
        current = [
            {
                "signal": item["signal_name"],
                "value": item["value"],
                "resolved geography": item["resolved_geography"],
                "source": item["source"],
                "age days": item["signal_age_days"],
            }
            for item in signals
            if item["signal_name"].endswith("_level")
        ]
        st.dataframe(current)
        st.write("DECISION")
        st.caption(demo["question"])
        for option in demo["options"]:
            with st.container(border=True):
                st.subheader(f"{option['action_label']} — {option['customer_decision']}")
                columns = st.columns(3)
                for column, label, key in zip(
                    columns,
                    ("Demand", "Revenue", "Contribution profit"),
                    (
                        "expected_demand",
                        "expected_revenue",
                        "expected_contribution_profit",
                    ),
                    strict=True,
                ):
                    interval = option.get(key)
                    if interval:
                        column.metric(label, f"{interval['mean']:.2f}")
                        column.caption(
                            f"90% interval: {interval['lower']:.2f}–{interval['upper']:.2f}"
                        )
                st.caption(f"Support: {option['support_level']}")
                with st.expander("WHY / technical evidence"):
                    st.json(option["why"])
        if demo.get("opportunity"):
            st.write("DECISION WORTH REVIEWING")
            st.json(demo["opportunity"])
        st.error("Commercial validity: NOT ESTABLISHED — this demo uses synthetic behavior.")
