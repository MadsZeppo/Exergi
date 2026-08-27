from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from decision_engine.benchmark.criteo_uplift import (
    CriteoBenchmarkConfig,
    policy_table,
    uplift_calibration,
    uplift_ranking_metrics,
)
from decision_engine.datasets.criteo_uplift import CriteoUpliftAdapter
from decision_engine.ledger import PredictionLedger


def _fixture(path: Path, rows: int = 2_000) -> None:
    rng = np.random.default_rng(42)
    treatment = rng.binomial(1, 0.85, rows)
    feature = rng.normal(size=rows)
    probability = np.clip(0.05 + 0.08 * treatment * (feature > 0), 0, 1)
    outcome = rng.binomial(1, probability)
    pl.DataFrame(
        {
            **{f"f{index}": feature + index / 100 for index in range(12)},
            "treatment": treatment,
            "conversion": outcome,
            "visit": np.maximum(outcome, rng.binomial(1, 0.1, rows)),
            "exposure": treatment * rng.binomial(1, 0.2, rows),
        }
    ).write_csv(path)


def test_criteo_adapter_schema_design_and_no_semantic_reinterpretation(tmp_path: Path) -> None:
    path = tmp_path / "criteo.csv"
    _fixture(path)
    adapter = CriteoUpliftAdapter(path)
    adapter.expected_rows = 2_000
    profile = adapter.validate()
    assert profile["rows"] == 2_000
    assert profile["missing_values"] == 0
    assert profile["design"]["assignment"] == "RANDOMIZED_BINARY"
    assert profile["design"]["estimand"] == "INTENTION_TO_TREAT"
    assert "exposure" not in adapter.feature_columns
    assert "conversion" not in adapter.feature_columns
    assert profile["exposure_feature_forbidden"] is True


def test_adapter_rejects_invalid_binary_outcome(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    _fixture(path, 100)
    frame = (
        pl.read_csv(path)
        .with_row_index()
        .with_columns(
            pl.when(pl.col("index") == 0)
            .then(2)
            .otherwise(pl.col("conversion"))
            .alias("conversion")
        )
        .drop("index")
    )
    frame.write_csv(path)
    adapter = CriteoUpliftAdapter(path)
    adapter.expected_rows = 100
    with pytest.raises(ValueError, match="non-binary"):
        adapter.validate()


def test_split_is_deterministic_and_disjoint(tmp_path: Path) -> None:
    path = tmp_path / "criteo.csv"
    _fixture(path)
    adapter = CriteoUpliftAdapter(path)
    ids = {
        split: set(adapter.split(adapter.scan(), split).select("row_id").collect()["row_id"])
        for split in ("train", "development", "test")
    }
    assert not (ids["train"] & ids["test"])
    assert not (ids["development"] & ids["test"])
    assert len(set.union(*ids.values())) == 2_000


def test_uplift_metrics_reward_true_responder_ranking() -> None:
    rng = np.random.default_rng(7)
    rows = 100_000
    responder = rng.binomial(1, 0.3, rows)
    treatment = rng.binomial(1, 0.5, rows)
    outcome = rng.binomial(1, 0.02 + treatment * responder * 0.15)
    good = uplift_ranking_metrics(outcome, treatment, responder.astype(float), 0.5)
    bad = uplift_ranking_metrics(outcome, treatment, -responder.astype(float), 0.5)
    assert good["auuc"] > bad["auuc"]
    assert good["qini"] > bad["qini"]


def test_policy_evaluation_beats_random_when_score_is_informative() -> None:
    rng = np.random.default_rng(8)
    rows = 100_000
    score = rng.uniform(size=rows)
    treatment = rng.binomial(1, 0.5, rows)
    outcome = rng.binomial(1, 0.01 + treatment * (score > 0.8) * 0.2)
    top = policy_table(outcome, treatment, score, (0.2,), 0.5)[0]
    assert float(top["policy_value"]) > float(top["random_policy_value"])
    assert float(top["incremental_conversions_vs_none"]) > 0


def test_uplift_calibration_has_ordered_intervals_and_all_rows() -> None:
    rng = np.random.default_rng(9)
    rows = 10_000
    treatment = rng.binomial(1, 0.5, rows)
    score = rng.normal(0.02, 0.01, rows)
    outcome = rng.binomial(1, np.clip(0.1 + treatment * score, 0, 1))
    calibration = uplift_calibration(outcome, treatment, score)
    assert sum(row["rows"] for row in calibration) == rows
    assert all(row["lower_90"] <= row["observed_uplift"] <= row["upper_90"] for row in calibration)


def test_frozen_batch_ledger_requires_freeze_record_before_evaluation(tmp_path: Path) -> None:
    ledger = PredictionLedger(tmp_path / "ledger.duckdb")
    ledger.append_frozen_batch(
        batch_id="batch",
        dataset_name="Criteo",
        dataset_version="v2.1",
        split="test",
        model_name="test",
        row_count=10,
        predictions_path="frozen.parquet",
        predictions_sha256="abc",
        config={"seed": 42},
        outcome_columns_hidden=("conversion", "visit"),
    )
    ledger.append_frozen_batch_evaluation("batch", {"qini": 0.1})
    row = ledger.connection.execute(
        "SELECT b.status, e.status FROM frozen_prediction_batches b "
        "JOIN frozen_batch_evaluations e USING(batch_id)"
    ).fetchone()
    assert row == ("FROZEN_BEFORE_REVEAL", "OUTCOMES_REVEALED")
    ledger.close()


def test_sample_size_configuration_and_metric_seed_determinism() -> None:
    config = CriteoBenchmarkConfig()
    assert config.sample_fractions == (0.01, 0.05, 0.10, 0.25, 0.50, 1.00)
    rng = np.random.default_rng(10)
    treatment = rng.binomial(1, 0.5, 1_000)
    outcome = rng.binomial(1, 0.05, 1_000)
    score = rng.normal(size=1_000)
    assert uplift_ranking_metrics(outcome, treatment, score, 0.5) == uplift_ranking_metrics(
        outcome, treatment, score, 0.5
    )
