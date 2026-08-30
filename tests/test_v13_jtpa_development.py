from __future__ import annotations

import json

import numpy as np

from benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.qualification import (
    ROOT,
)
from benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.report import (
    STATUS,
    render_reports,
)
from benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.tournament import (
    PROPENSITY,
    dr_score,
    effective_sample_size,
    hajek_value,
)


def _json(name: str) -> dict[str, object]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_v13_known_propensity_policy_estimators_recover_observed_actions() -> None:
    y = np.asarray([10.0, 30.0, 20.0, 40.0])
    treatment = np.asarray([0, 1, 0, 1], dtype=np.int8)
    policy = np.ones(4, dtype=np.int8)
    point, influence = hajek_value(policy, y, treatment)
    assert point == np.mean(y[treatment == 1])
    assert len(influence) == len(y)

    m0 = np.asarray([10.0, 10.0, 20.0, 20.0])
    m1 = np.asarray([30.0, 30.0, 40.0, 40.0])
    score = dr_score(policy, y, treatment, m0, m1)
    expected = m1 + (treatment == 1) * (y - m1) / PROPENSITY
    assert np.allclose(score, expected)


def test_v13_effective_sample_size_handles_zero_and_uniform_weights() -> None:
    assert effective_sample_size(np.zeros(4)) == 0.0
    assert effective_sample_size(np.ones(4)) == 4.0


def test_v13_persisted_development_result_does_not_authorize_reveal() -> None:
    result = _json("V13_MODEL_TOURNAMENT.json")
    access = _json("manifests/V13_DEVELOPMENT_ACCESS.json")
    assert result["development_status"] == STATUS
    assert result["earned_validation_reveal"] is False
    assert result["access_control"]["validation_outcomes_opened"] is False
    assert access["validation_outcomes_opened"] is False
    assert access["validation_outcome_bytes_opened"] == 0
    assert all(not model["pre_placebo_pass"] for model in result["models"].values())


def test_v13_placebos_are_frozen_development_only_failures() -> None:
    result = _json("V13_PLACEBO_RESULTS.json")
    assert result["validation_outcomes_opened"] is False
    assert result["treatment_shuffle_within_site"]["replicates"] == 20
    assert result["outcome_shuffle"]["replicates"] == 20
    assert result["passed_both_placebos"] is False


def test_v13_report_generation_is_deterministic_and_has_no_reveal_artifact() -> None:
    first = render_reports()
    second = render_reports()
    assert first == second
    assert first["V13_DEVELOPMENT_QA.json"].endswith("\n")
    assert not any("FREEZE" in name or "VALIDATION" in name for name in first)
