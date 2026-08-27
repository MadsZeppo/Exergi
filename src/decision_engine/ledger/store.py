"""Append-only DuckDB prediction ledger."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from commercial_twin.schemas import TwinCalibrationRecord
from decision_engine.core import SimulationResult
from decision_engine.schemas import DecisionPrediction, PredictionEvaluation


class PredictionLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(str(self.path))
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
              prediction_id VARCHAR PRIMARY KEY, decision_id VARCHAR, created_at TIMESTAMPTZ,
              data_cutoff TIMESTAMPTZ, dataset_name VARCHAR, dataset_version VARCHAR,
              model_name VARCHAR, model_version VARCHAR, config_hash VARCHAR,
              git_commit VARCHAR, random_seed BIGINT, state_snapshot_hash VARCHAR,
              candidate_actions JSON, expected_outcomes JSON, uncertainty JSON,
              recommended_action VARCHAR, confidence JSON, assumptions JSON, warnings JSON
            );
            CREATE TABLE IF NOT EXISTS evaluations (
              prediction_id VARCHAR PRIMARY KEY REFERENCES predictions(prediction_id),
              evaluated_at TIMESTAMPTZ, actual_action VARCHAR, actual_outcome DOUBLE,
              forecast_metrics JSON, calibration_metrics JSON,
              regret_type VARCHAR, regret_value DOUBLE
            );
            CREATE TABLE IF NOT EXISTS simulation_predictions (
              simulation_id VARCHAR PRIMARY KEY, twin_id VARCHAR, decision_id VARCHAR,
              created_at TIMESTAMPTZ, state_snapshot_hash VARCHAR, action JSON,
              outcome_distributions JSON, disposition VARCHAR, evidence JSON,
              support JSON, uncertainty JSON, assumptions JSON, model_versions JSON
            );
            CREATE TABLE IF NOT EXISTS simulation_evaluations (
              simulation_id VARCHAR PRIMARY KEY REFERENCES simulation_predictions(simulation_id),
              evaluated_at TIMESTAMPTZ, predicted JSON, actual JSON, errors JSON
            );
            CREATE TABLE IF NOT EXISTS frozen_prediction_batches (
              batch_id VARCHAR PRIMARY KEY, created_at TIMESTAMPTZ, dataset_name VARCHAR,
              dataset_version VARCHAR, split VARCHAR, model_name VARCHAR, row_count BIGINT,
              predictions_path VARCHAR, predictions_sha256 VARCHAR, config_hash VARCHAR,
              outcome_columns_hidden JSON, status VARCHAR
            );
            CREATE TABLE IF NOT EXISTS frozen_batch_evaluations (
              batch_id VARCHAR PRIMARY KEY REFERENCES frozen_prediction_batches(batch_id),
              evaluated_at TIMESTAMPTZ, metrics JSON, status VARCHAR
            );
            CREATE TABLE IF NOT EXISTS twin_query_records (
              query_id VARCHAR PRIMARY KEY, created_at TIMESTAMPTZ, as_of TIMESTAMPTZ,
              query_plan JSON, snapshot_version VARCHAR, model_version VARCHAR,
              answer_distribution JSON, evidence_type VARCHAR, validation_status VARCHAR,
              action JSON, treatment JSON, predicted_incremental_effect JSON,
              economic_estimate JSON, decision_state VARCHAR, realized_outcome JSON,
              calibration_update JSON
            );
        """)

    @staticmethod
    def stable_hash(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def append_prediction(
        self,
        prediction: DecisionPrediction,
        *,
        dataset_name: str,
        dataset_version: str,
        model_name: str,
        config: dict[str, Any],
        random_seed: int,
        state_snapshot: dict[str, Any],
        git_commit: str | None = None,
        prediction_id: str | None = None,
    ) -> str:
        identifier = prediction_id or str(uuid4())
        distributions = [item.model_dump(mode="json") for item in prediction.action_distributions]
        self.connection.execute(
            "INSERT INTO predictions VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                identifier,
                prediction.decision_id,
                prediction.created_at,
                prediction.data_cutoff,
                dataset_name,
                dataset_version,
                model_name,
                prediction.model_version,
                self.stable_hash(config),
                git_commit,
                random_seed,
                self.stable_hash(state_snapshot),
                json.dumps([d["action_id"] for d in distributions]),
                json.dumps(distributions),
                json.dumps(
                    {
                        d["action_id"]: {k: v for k, v in d.items() if k.startswith("p")}
                        for d in distributions
                    }
                ),
                prediction.recommended_action,
                json.dumps([d["evidence_status"] for d in distributions]),
                json.dumps(prediction.assumptions),
                json.dumps(prediction.warnings),
            ],
        )
        return identifier

    def append_evaluation(
        self,
        prediction_id: str,
        evaluation: PredictionEvaluation,
        forecast_metrics: dict[str, float],
        calibration_metrics: dict[str, Any],
    ) -> None:
        self.connection.execute(
            "INSERT INTO evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                prediction_id,
                datetime.now(UTC),
                evaluation.actual_action,
                evaluation.actual_outcome,
                json.dumps(forecast_metrics),
                json.dumps(calibration_metrics),
                evaluation.regret_type,
                evaluation.regret_value,
            ],
        )

    def append_simulation(self, result: SimulationResult, *, twin_id: str) -> None:
        self.connection.execute(
            "INSERT INTO simulation_predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                result.simulation_id,
                twin_id,
                result.decision_id,
                result.generated_at,
                self.stable_hash(result.state_snapshot.model_dump(mode="json")),
                json.dumps(result.candidate_action.model_dump(mode="json")),
                json.dumps([item.model_dump(mode="json") for item in result.outcome_distributions]),
                result.disposition.value,
                json.dumps(result.evidence),
                json.dumps(result.support),
                json.dumps(result.uncertainty),
                json.dumps(result.assumptions),
                json.dumps(result.model_versions),
            ],
        )

    def append_simulation_evaluation(self, record: TwinCalibrationRecord) -> None:
        self.connection.execute(
            "INSERT INTO simulation_evaluations VALUES (?, ?, ?, ?, ?)",
            [
                record.simulation_id,
                record.recorded_at,
                json.dumps(record.predicted),
                json.dumps(record.actual),
                json.dumps(record.errors),
            ],
        )

    def append_frozen_batch(
        self,
        *,
        batch_id: str,
        dataset_name: str,
        dataset_version: str,
        split: str,
        model_name: str,
        row_count: int,
        predictions_path: str,
        predictions_sha256: str,
        config: dict[str, Any],
        outcome_columns_hidden: tuple[str, ...],
    ) -> None:
        self.connection.execute(
            "INSERT INTO frozen_prediction_batches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                batch_id,
                datetime.now(UTC),
                dataset_name,
                dataset_version,
                split,
                model_name,
                row_count,
                predictions_path,
                predictions_sha256,
                self.stable_hash(config),
                json.dumps(outcome_columns_hidden),
                "FROZEN_BEFORE_REVEAL",
            ],
        )

    def append_frozen_batch_evaluation(self, batch_id: str, metrics: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO frozen_batch_evaluations VALUES (?, ?, ?, ?)",
            [batch_id, datetime.now(UTC), json.dumps(metrics), "OUTCOMES_REVEALED"],
        )

    def append_twin_query(
        self,
        *,
        query_id: str,
        as_of: datetime,
        query_plan: dict[str, Any],
        snapshot_version: str,
        model_version: str,
        answer_distribution: dict[str, Any],
        evidence_type: str,
        validation_status: str,
        action: dict[str, Any] | None = None,
        treatment: dict[str, Any] | None = None,
        predicted_incremental_effect: dict[str, Any] | None = None,
        economic_estimate: dict[str, Any] | None = None,
        decision_state: str | None = None,
    ) -> None:
        """Freeze a query/action answer; realized fields are intentionally append-later."""
        self.connection.execute(
            "INSERT INTO twin_query_records VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
            [
                query_id,
                datetime.now(UTC),
                as_of,
                json.dumps(query_plan),
                snapshot_version,
                model_version,
                json.dumps(answer_distribution),
                evidence_type,
                validation_status,
                json.dumps(action) if action is not None else None,
                json.dumps(treatment) if treatment is not None else None,
                json.dumps(predicted_incremental_effect)
                if predicted_incremental_effect is not None
                else None,
                json.dumps(economic_estimate) if economic_estimate is not None else None,
                decision_state,
            ],
        )

    def append_twin_query_outcome(
        self,
        query_id: str,
        *,
        realized_outcome: dict[str, Any],
        calibration_update: dict[str, Any],
    ) -> None:
        existing = self.connection.execute(
            "SELECT realized_outcome IS NULL FROM twin_query_records WHERE query_id = ?",
            [query_id],
        ).fetchone()
        if existing is None or not existing[0]:
            raise ValueError("query outcome missing, already appended, or immutable")
        self.connection.execute(
            "UPDATE twin_query_records SET realized_outcome = ?, calibration_update = ? "
            "WHERE query_id = ? AND realized_outcome IS NULL",
            [json.dumps(realized_outcome), json.dumps(calibration_update), query_id],
        )

    def close(self) -> None:
        self.connection.close()
