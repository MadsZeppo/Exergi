from __future__ import annotations

import inspect

import numpy as np
import pytest

from benchmarks.ecommerce_decision_layer_v14_multichannel_proof import models
from benchmarks.ecommerce_decision_layer_v14_multichannel_proof.models import (
    ObservedTrainingData,
    customer_fold,
    evaluate_policy,
    policy_from_effects,
)


def _data(n: int = 1_000) -> ObservedTrainingData:
    assignment = np.arange(n, dtype=np.int8) % 10
    features = np.zeros((n, 26), dtype=float)
    candidate = np.full((n, 10), 0.1)
    return ObservedTrainingData(
        features=features,
        outcome=assignment.astype(float) * 0.1,
        gross_revenue=np.zeros(n),
        assignment=assignment,
        logged_propensity=np.full(n, 0.1),
        candidate_propensity=candidate,
        eligible_actions=np.ones((n, 10), dtype=bool),
        cost_complete=np.ones((n, 10), dtype=bool),
        data_valid=np.ones(n, dtype=bool),
        customer_ids=np.asarray([f"M_C{index:05d}" for index in range(n)]),
        merchant_ids=np.full(n, "M"),
        merchant_families=np.full(n, "FASHION"),
        weeks=np.ones(n, dtype=np.int16),
        maturity_weeks=np.full(n, 5),
    )


def test_v14_customer_fold_keeps_repeated_customer_together() -> None:
    identifiers = np.asarray(["a", "b", "a", "c", "b"])
    folds = customer_fold(identifiers)
    assert folds[0] == folds[2]
    assert folds[1] == folds[4]


def test_v14_known_propensity_policy_value_recovers_action_contrast() -> None:
    data = _data()
    policy = np.full(len(data.outcome), 9, dtype=np.int8)
    bau = np.zeros(len(data.outcome), dtype=np.int8)
    nuisance = np.broadcast_to(np.arange(10) * 0.1, (len(data.outcome), 10)).copy()
    result = evaluate_policy(policy, bau, data, nuisance)
    assert result["hajek_ipw"].point == pytest.approx(0.9)
    assert result["doubly_robust"].point == pytest.approx(0.9)


def test_v14_policy_blocks_unsupported_missing_cost_and_invalid_rows() -> None:
    data = _data(100)
    effects = np.zeros((100, 10))
    effects[:, 1] = 10.0
    unsupported = data.candidate_propensity.copy()
    unsupported[:, 1] = 0.001
    blocked = ObservedTrainingData(
        **{
            **{name: getattr(data, name) for name in data.__dataclass_fields__},
            "candidate_propensity": unsupported,
        }
    )
    policy = policy_from_effects(effects, blocked, {"FASHION": 0.4})
    assert np.all(policy == 0)


def test_v14_model_module_has_no_evaluator_import_or_oracle_dependency() -> None:
    source = inspect.getsource(models)
    assert "evaluator_only" not in source
    assert "potential_contribution_profit" not in source


def test_v14_identical_bau_policy_has_zero_effect_and_unit_p_value() -> None:
    data = _data()
    bau = np.zeros(len(data.outcome), dtype=np.int8)
    nuisance = np.broadcast_to(np.arange(10) * 0.1, (len(data.outcome), 10)).copy()
    result = evaluate_policy(bau, bau, data, nuisance)
    assert result["hajek_ipw"].point == 0.0
    assert result["hajek_ipw"].p_value_two_sided == 1.0
    assert result["doubly_robust"].p_value_two_sided == 1.0
