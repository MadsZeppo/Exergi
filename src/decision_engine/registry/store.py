from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb


class ModelPerformanceRegistry:
    def __init__(self, path: str | Path) -> None:
        self.connection = duckdb.connect(str(path))
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS model_performance (
              record_id VARCHAR PRIMARY KEY, model VARCHAR, dataset VARCHAR, regime VARCHAR,
              decision_type VARCHAR, metrics JSON, recorded_at TIMESTAMPTZ, model_version VARCHAR
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS decision_performance_v2 (
              record_id VARCHAR PRIMARY KEY, decision_type VARCHAR, action_type VARCHAR,
              model VARCHAR, calibration JSON, outcome_errors JSON,
              economic_regret DOUBLE, support_regime VARCHAR, recorded_at TIMESTAMPTZ
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS behavior_model_tournament_v1 (
              record_id VARCHAR PRIMARY KEY, decision_type VARCHAR, data_regime VARCHAR,
              model VARCHAR, factual_error JSON, causal_error JSON, calibration JSON,
              economic_regret DOUBLE, metadata JSON, recorded_at TIMESTAMPTZ
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS decision_model_defaults_v1 (
              decision_type VARCHAR PRIMARY KEY, model VARCHAR, selection_artifact VARCHAR,
              development_only BOOLEAN, customer_facing_do_this_enabled BOOLEAN,
              recorded_at TIMESTAMPTZ
            )
        """)

    def append(
        self,
        *,
        record_id: str,
        model: str,
        dataset: str,
        regime: str,
        decision_type: str,
        metrics: dict[str, float],
        model_version: str,
    ) -> None:
        self.connection.execute(
            "INSERT INTO model_performance VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record_id,
                model,
                dataset,
                regime,
                decision_type,
                json.dumps(metrics),
                datetime.now(UTC),
                model_version,
            ],
        )

    def records(self) -> list[tuple[object, ...]]:
        return self.connection.execute(
            "SELECT * FROM model_performance ORDER BY recorded_at"
        ).fetchall()

    def append_decision_performance(
        self,
        *,
        record_id: str,
        decision_type: str,
        action_type: str,
        model: str,
        calibration: dict[str, object],
        outcome_errors: dict[str, float],
        support_regime: str,
        economic_regret: float | None = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO decision_performance_v2 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record_id,
                decision_type,
                action_type,
                model,
                json.dumps(calibration),
                json.dumps(outcome_errors),
                economic_regret,
                support_regime,
                datetime.now(UTC),
            ],
        )

    def close(self) -> None:
        self.connection.close()

    def append_behavior_model_result(
        self,
        *,
        record_id: str,
        decision_type: str,
        data_regime: str,
        model: str,
        factual_error: dict[str, float],
        causal_error: dict[str, float],
        calibration: dict[str, object],
        economic_regret: float | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO behavior_model_tournament_v1 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record_id,
                decision_type,
                data_regime,
                model,
                json.dumps(factual_error),
                json.dumps(causal_error),
                json.dumps(calibration),
                economic_regret,
                json.dumps(metadata or {}),
                datetime.now(UTC),
            ],
        )

    def set_decision_model_default(
        self,
        *,
        decision_type: str,
        model: str,
        selection_artifact: str,
        customer_facing_do_this_enabled: bool,
    ) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO decision_model_defaults_v1 VALUES (?, ?, ?, ?, ?, ?)",
            [
                decision_type,
                model,
                selection_artifact,
                True,
                customer_facing_do_this_enabled,
                datetime.now(UTC),
            ],
        )

    def selected_model(self, decision_type: str) -> str | None:
        row = self.connection.execute(
            "SELECT model FROM decision_model_defaults_v1 WHERE decision_type = ?",
            [decision_type],
        ).fetchone()
        return str(row[0]) if row is not None else None
