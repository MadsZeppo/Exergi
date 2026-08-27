from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from commercial_twin.behavior import BehaviorModel
from commercial_twin.schemas import (
    CommercialAction,
    CommercialOutcome,
    CommercialState,
    CommercialTwinSnapshot,
    TwinCalibrationRecord,
    TwinReadinessReport,
)
from decision_engine.core import CandidateAction, DecisionState, SimulationResult
from decision_engine.ledger import PredictionLedger
from decision_engine.registry import ModelPerformanceRegistry


class CommercialTwin:
    def __init__(
        self,
        twin_id: str,
        state: CommercialState,
        behavior_models: dict[str, BehaviorModel],
        readiness_report: TwinReadinessReport,
        *,
        ledger: PredictionLedger | None = None,
        registry: ModelPerformanceRegistry | None = None,
    ) -> None:
        self.twin_id = twin_id
        self.state = state
        self.behavior_models = dict(behavior_models)
        self._readiness_report = readiness_report
        self.ledger = ledger
        self.registry = registry
        self._calibration: list[TwinCalibrationRecord] = []
        self._results: dict[str, SimulationResult] = {}

    def snapshot(self) -> CommercialTwinSnapshot:
        versions = {
            name: getattr(model, "model_version", "unknown")
            for name, model in self.behavior_models.items()
        }
        return CommercialTwinSnapshot(
            twin_id=self.twin_id,
            state=self.state,
            model_versions=versions,
            created_at=datetime.now(UTC),
        )

    def simulate(self, action: CommercialAction) -> SimulationResult:
        if action.action_type not in self.behavior_models:
            raise ValueError(f"no behavior model for action type {action.action_type!r}")
        prediction = self.behavior_models[action.action_type].predict_outcomes(self.state, action)
        result = SimulationResult(
            simulation_id=str(uuid4()),
            decision_id=f"{self.twin_id}:{action.action_id}",
            state_snapshot=DecisionState(
                state_id=self.twin_id,
                values=self.state.model_dump(mode="json"),
                observed_at=self.state.as_of,
            ),
            candidate_action=CandidateAction(
                action_id=action.action_id,
                action_type=action.action_type,
                parameters=action.model_dump(mode="json"),
            ),
            outcome_distributions=prediction.distributions,
            disposition=prediction.disposition,
            evidence=prediction.evidence,
            support=prediction.support,
            uncertainty=prediction.uncertainty,
            assumptions=prediction.assumptions,
            model_versions=prediction.model_versions,
            generated_at=datetime.now(UTC),
            experiment=prediction.experiment,
        )
        self._results[result.simulation_id] = result
        if self.ledger is not None:
            self.ledger.append_simulation(result, twin_id=self.twin_id)
        return result

    def compare(self, actions: tuple[CommercialAction, ...]) -> tuple[SimulationResult, ...]:
        if not actions:
            raise ValueError("at least one action is required")
        return tuple(self.simulate(action) for action in actions)

    def readiness(self) -> TwinReadinessReport:
        return self._readiness_report

    def calibration(self) -> tuple[TwinCalibrationRecord, ...]:
        return tuple(self._calibration)

    def update(
        self, simulation_id: str, outcomes: tuple[CommercialOutcome, ...]
    ) -> TwinCalibrationRecord:
        result = self._results.get(simulation_id)
        if result is None:
            raise KeyError(f"unknown simulation {simulation_id}")
        predicted = {item.outcome_name: item.mean for item in result.outcome_distributions}
        actual = {item.outcome_name: item.value for item in outcomes}
        shared = predicted.keys() & actual.keys()
        errors = {name: actual[name] - predicted[name] for name in shared}
        record = TwinCalibrationRecord(
            simulation_id=simulation_id,
            twin_id=self.twin_id,
            action_id=result.candidate_action.action_id,
            predicted=predicted,
            actual=actual,
            errors=errors,
            recorded_at=datetime.now(UTC),
        )
        self._calibration.append(record)
        if self.ledger is not None:
            self.ledger.append_simulation_evaluation(record)
        if self.registry is not None:
            self.registry.append_decision_performance(
                record_id=str(uuid4()),
                decision_type="commercial_twin",
                action_type=result.candidate_action.action_type,
                model=result.model_versions.get(result.candidate_action.action_type, "unknown"),
                outcome_errors=errors,
                calibration={"records": len(self._calibration)},
                support_regime=str(result.support.get("support_level", "unknown")),
            )
        return record

    def diagnostics(self) -> dict[str, Any]:
        return {name: model.diagnostics() for name, model in self.behavior_models.items()}
