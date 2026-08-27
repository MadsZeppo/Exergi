from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class DevelopmentCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_name: str
    policy_value: float
    calibration_error: float = Field(ge=0)
    policy_name: str
    metadata: dict[str, float | str] = Field(default_factory=dict)


class DevelopmentSelectionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_type: str
    calibration_tolerance: float = Field(gt=0)
    selection_metric: str = "maximum development policy value among calibrated candidates"


class FrozenModelSelection(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_type: str
    selected_model: str
    selected_policy: str
    development_policy_value: float
    development_calibration_error: float
    eligible_models: tuple[str, ...]
    rejected_for_calibration: tuple[str, ...]
    candidates: tuple[DevelopmentCandidate, ...]
    frozen_at: datetime
    test_metrics_used_for_selection: bool = False


def select_development_model(
    candidates: tuple[DevelopmentCandidate, ...],
    config: DevelopmentSelectionConfig,
) -> FrozenModelSelection:
    if not candidates:
        raise ValueError("at least one development candidate is required")
    best_calibration = min(item.calibration_error for item in candidates)
    eligible = tuple(
        item
        for item in candidates
        if item.calibration_error <= best_calibration + config.calibration_tolerance
    )
    if not eligible:
        raise ValueError("no model passes the calibration guardrail")
    selected = max(eligible, key=lambda item: (item.policy_value, -item.calibration_error))
    return FrozenModelSelection(
        decision_type=config.decision_type,
        selected_model=selected.model_name,
        selected_policy=selected.policy_name,
        development_policy_value=selected.policy_value,
        development_calibration_error=selected.calibration_error,
        eligible_models=tuple(item.model_name for item in eligible),
        rejected_for_calibration=tuple(
            item.model_name for item in candidates if item not in eligible
        ),
        candidates=candidates,
        frozen_at=datetime.now(UTC),
    )


class GateBenchmark(BaseModel):
    model_config = ConfigDict(frozen=True)
    gated_policy_value: float
    ungated_policy_value: float
    simple_targeting_value: float
    treat_all_value: float
    treat_none_value: float

    def gate_wins(self) -> bool:
        return self.gated_policy_value > max(
            self.ungated_policy_value,
            self.simple_targeting_value,
            self.treat_all_value,
            self.treat_none_value,
        )


class CustomerFacingGateDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_type: str
    development: GateBenchmark
    final_test: GateBenchmark
    customer_facing_do_this_enabled: bool
    internal_labels_enabled: tuple[str, ...] = (
        "TEST THIS",
        "NOT ENOUGH EVIDENCE",
    )
    reason: str


def promote_customer_facing_gate(
    decision_type: str,
    development: GateBenchmark,
    final_test: GateBenchmark,
) -> CustomerFacingGateDecision:
    enabled = development.gate_wins() and final_test.gate_wins()
    return CustomerFacingGateDecision(
        decision_type=decision_type,
        development=development,
        final_test=final_test,
        customer_facing_do_this_enabled=enabled,
        reason=(
            "gate beat every required comparator on development and untouched test"
            if enabled
            else "DO THIS disabled: gate did not beat every required comparator on both splits"
        ),
    )
