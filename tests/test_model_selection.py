from decision_engine.decision.model_selection import (
    DevelopmentCandidate,
    DevelopmentSelectionConfig,
    GateBenchmark,
    promote_customer_facing_gate,
    select_development_model,
)


def test_selection_uses_development_policy_value_with_calibration_guardrail() -> None:
    selection = select_development_model(
        (
            DevelopmentCandidate(
                model_name="high_value_bad_calibration",
                policy_value=10,
                calibration_error=0.5,
                policy_name="top_20",
            ),
            DevelopmentCandidate(
                model_name="best_eligible",
                policy_value=8,
                calibration_error=0.02,
                policy_name="top_20",
            ),
            DevelopmentCandidate(
                model_name="calibrated_lower_value",
                policy_value=7,
                calibration_error=0.01,
                policy_name="top_20",
            ),
        ),
        DevelopmentSelectionConfig(decision_type="campaign", calibration_tolerance=0.02),
    )
    assert selection.selected_model == "best_eligible"
    assert selection.test_metrics_used_for_selection is False
    assert selection.rejected_for_calibration == ("high_value_bad_calibration",)


def test_customer_facing_gate_is_fail_closed_on_either_split() -> None:
    winning = GateBenchmark(
        gated_policy_value=5,
        ungated_policy_value=4,
        simple_targeting_value=3,
        treat_all_value=2,
        treat_none_value=1,
    )
    losing = winning.model_copy(update={"treat_all_value": 6})
    disabled = promote_customer_facing_gate("campaign", winning, losing)
    assert not disabled.customer_facing_do_this_enabled
    assert disabled.internal_labels_enabled == ("TEST THIS", "NOT ENOUGH EVIDENCE")
    enabled = promote_customer_facing_gate("campaign", winning, winning)
    assert enabled.customer_facing_do_this_enabled
