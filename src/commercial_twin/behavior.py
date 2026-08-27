from __future__ import annotations

from typing import Any, Protocol

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from commercial_twin.schemas import CommercialAction, CommercialState
from decision_engine.core import DecisionDisposition, OutcomeDistribution


class BehaviorPrediction(BaseModel):
    model_config = ConfigDict(frozen=True)
    distributions: tuple[OutcomeDistribution, ...]
    disposition: DecisionDisposition
    evidence: dict[str, Any] = Field(default_factory=dict)
    support: dict[str, Any] = Field(default_factory=dict)
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    model_versions: dict[str, str] = Field(default_factory=dict)
    experiment: dict[str, Any] | None = None


class BehaviorModel(Protocol):
    action_type: str

    def fit(self, history: pl.DataFrame) -> BehaviorModel: ...

    def predict_outcomes(
        self, state: CommercialState, action: CommercialAction
    ) -> BehaviorPrediction: ...

    def diagnostics(self) -> dict[str, Any]: ...

    def calibration_report(self) -> dict[str, Any]: ...
