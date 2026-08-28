from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from benchmarks.ecommerce_decision_layer_v7_2.buy_baits_development import (
    run as run_buy_baits_development,
)
from benchmarks.ecommerce_decision_layer_v7_2.buy_baits_development import verify_lock
from decision_engine.datasets.buy_baits import (
    ACTION_GOVERNANCE,
    DATA_COLUMNS,
    ENTERPRISE_ALLOWED_ARMS,
    SCIENTIFIC_ALL_ARMS,
    VARIABLE_TIMING,
    GovernanceStatus,
    VariableTiming,
    development_frame_from_audit,
    policy_dataset_from_development,
)
from decision_engine.economic_policy_v72 import (
    ClaimAuthority,
    ClaimLevel,
    DRPseudoOutcomeModel,
    causal_challengers,
)
from decision_engine.economic_policy_v72.splits import stable_unit_hash


def _row(
    unit: int, treatment: int, *, purchase: float = 0, profit: float = np.nan
) -> dict[str, object]:
    return {
        "id": float(unit),
        "date": 1.0,
        "treatment": treatment,
        "purchase": purchase,
        "red": np.nan,
        "purchasevalue": np.nan,
        "profit": profit,
        "counting": np.nan,
        "device": "desktop" if unit % 2 else "mobile",
        "sessions": 1.0,
        "out_num90": 0.0,
        "income_cat": 0.0,
    }


def test_all_buy_baits_variables_have_fail_closed_timing() -> None:
    assert set(VARIABLE_TIMING) == set(DATA_COLUMNS)
    assert VARIABLE_TIMING["device"] is VariableTiming.PRETREATMENT_ALLOWED
    assert VARIABLE_TIMING["sessions"] is VariableTiming.POST_TREATMENT_FORBIDDEN_FEATURE
    assert VARIABLE_TIMING["income_cat"] is VariableTiming.UNKNOWN_FORBIDDEN
    assert VARIABLE_TIMING["out_num90"] is VariableTiming.UNKNOWN_FORBIDDEN


def test_governance_is_mechanics_based_and_enterprise_excludes_friction_arms() -> None:
    assert SCIENTIFIC_ALL_ARMS == tuple(range(1, 9))
    assert ENTERPRISE_ALLOWED_ARMS == (1, 4, 7, 8)
    assert ACTION_GOVERNANCE[2] is GovernanceStatus.PROHIBITED
    assert ACTION_GOVERNANCE[3] is GovernanceStatus.RESTRICTED
    assert ACTION_GOVERNANCE[8] is GovernanceStatus.ALLOWED


def test_development_materialization_hashes_ids_and_filters_before_persisting() -> None:
    frame = pd.DataFrame([_row(1, 1), _row(2, 8)], columns=DATA_COLUMNS)
    wanted = {stable_unit_hash("buy_baits_v1", "1")}
    development = development_frame_from_audit(frame, wanted)
    assert "id" not in development
    assert development["unit_hash"].tolist() == list(wanted)
    assert development["treatment"].tolist() == [1]


def test_policy_adapter_uses_only_pretreatment_device_and_complete_profit() -> None:
    raw = pd.DataFrame(
        [
            _row(1, 1, purchase=1, profit=2.0),
            _row(2, 8),
            _row(3, 4, purchase=1, profit=np.nan),
        ],
        columns=DATA_COLUMNS,
    )
    hashes = {stable_unit_hash("buy_baits_v1", str(unit)) for unit in (1, 2, 3)}
    development = development_frame_from_audit(raw, hashes)
    data = policy_dataset_from_development(development)
    assert data.feature_names == ("device=desktop", "device=mobile", "device=tablet")
    assert len(data.action) == 2
    assert np.all(np.isfinite(data.monetary_outcome))
    assert np.all(data.allowed_actions[:, [0, 3, 6, 7]])
    assert not np.any(data.allowed_actions[:, [1, 2, 4, 5]])


def test_observed_retailer_profit_allows_level_three_but_not_contribution_profit() -> None:
    authority = ClaimAuthority(
        level=ClaimLevel.REAL_RANDOMIZED_ECONOMIC_VALUE_UNDER_DECLARED_COSTS,
        randomized=True,
        real_world=True,
        monetary_outcome=True,
        observed_revenue=True,
        observed_profit=True,
        label="package-provided retailer profit",
    )
    assert authority.level is ClaimLevel.REAL_RANDOMIZED_ECONOMIC_VALUE_UNDER_DECLARED_COSTS
    with pytest.raises(ValueError, match="cost components"):
        ClaimAuthority(
            level=ClaimLevel.REAL_RANDOMIZED_CONTRIBUTION_PROFIT,
            randomized=True,
            real_world=True,
            monetary_outcome=True,
            observed_revenue=True,
            observed_profit=True,
            label="contribution profit",
        )


def test_development_runner_has_no_validation_or_sealed_data_path() -> None:
    runner = Path(
        "benchmarks/ecommerce_decision_layer_v7_2/buy_baits_development.py"
    ).read_text()
    assert "development.parquet" in runner
    assert "validation.parquet" not in runner
    assert "sealed_test.parquet" not in runner
    assert "data/data.dta" not in runner


def test_buy_baits_negative_control_lock_is_valid_and_blocks_retuning() -> None:
    assert verify_lock()
    with pytest.raises(RuntimeError, match="immutable"):
        run_buy_baits_development()


@pytest.mark.parametrize("challenger", causal_challengers(seed=17))
def test_causal_challengers_return_finite_all_arm_predictions(challenger: object) -> None:
    rng = np.random.default_rng(17)
    features = rng.normal(size=(400, 3))
    action = rng.integers(0, 8, size=400, dtype=np.int64)
    outcome = 0.02 + 0.01 * features[:, 0] + 0.005 * (action == 1) + rng.normal(
        0, 0.01, 400
    )
    challenger.fit(features, action, outcome, 8)  # type: ignore[attr-defined]
    prediction = challenger.predict_actions(features[:20])  # type: ignore[attr-defined]
    assert prediction.shape == (20, 8)
    assert np.all(np.isfinite(prediction))
    if isinstance(challenger, DRPseudoOutcomeModel):
        assert challenger.nuisance_ is not None
        assert challenger.nuisance_.fold_id_ is not None
        assert np.all(challenger.nuisance_.fold_id_ >= 0)
