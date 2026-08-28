from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from benchmarks.ecommerce_decision_layer_v7_2.hillstrom_static_audit import (
    DEVELOPMENT,
    MANIFEST,
    PRIMARY_COST,
    QUARANTINE_OUTPUT,
    _aipw,
    _bootstrap_difference,
    _cuped,
    _folds,
    _ols_hc3,
    _policy_hierarchy,
    _welch,
)
from decision_engine.economic_policy_v72.splits import stable_unit_hash


def test_estimators_recover_same_randomized_mean_estimand() -> None:
    rng = np.random.default_rng(731)
    n = 2_000
    treatment = np.tile(np.array([0, 1]), n // 2)
    x = rng.normal(size=(n, 3))
    history = 3 * x[:, 0] + rng.normal(size=n)
    y = 2.0 * treatment + x[:, 0] + rng.normal(size=n)
    folds = _folds(np.asarray([f"unit-{index}" for index in range(n)]))

    estimates = (
        _welch(y, treatment),
        _cuped(y, treatment, history),
        _ols_hc3(y, treatment, x),
        _aipw(y, treatment, x, folds)[0],
    )
    assert all(abs(estimate.point - 2.0) < 0.15 for estimate in estimates)
    assert all(estimate.lower_95 <= estimate.point <= estimate.upper_95 for estimate in estimates)


def test_customer_bootstrap_is_deterministic_and_matches_analytic_se() -> None:
    rng = np.random.default_rng(81)
    treatment = np.repeat(np.array([0, 1]), 400)
    y = rng.normal(loc=treatment * 0.5, scale=1.0)
    first, _ = _bootstrap_difference(y, treatment, 300, np.random.default_rng(99))
    second, _ = _bootstrap_difference(y, treatment, 300, np.random.default_rng(99))
    analytic = _welch(y, treatment)

    assert first == second
    assert first.lower_95 <= first.point <= first.upper_95
    assert 0.8 <= analytic.standard_error / first.standard_error <= 1.25


def test_audit_has_no_validation_or_sealed_outcome_input() -> None:
    assert DEVELOPMENT == Path("data/processed/hillstrom/v7_2/development.parquet")
    source = Path("benchmarks/ecommerce_decision_layer_v7_2/hillstrom_static_audit.py").read_text()
    assert "validation.parquet" not in source.lower()
    assert "sealed_test.parquet" not in source.lower()


def test_quarantined_row_stays_in_original_sealed_split() -> None:
    manifest = json.loads(MANIFEST.read_text())
    row_zero = stable_unit_hash("hillstrom", "row-0")
    assert row_zero in set(manifest["unit_hashes"]["SEALED_TEST"])
    assert row_zero not in set(manifest["unit_hashes"]["DEVELOPMENT"])
    assert row_zero not in set(manifest["unit_hashes"]["VALIDATION"])
    if QUARANTINE_OUTPUT.exists():
        quarantine = json.loads(QUARANTINE_OUTPUT.read_text())
        assert quarantine["split_moved"] is False
        assert quarantine["sealed_test_fully_untouched"] is False


def test_policy_hierarchy_fails_closed_when_static_gate_fails() -> None:
    prior = json.loads(
        Path(
            "benchmarks/ecommerce_decision_layer_v7_2/results/hillstrom_development_tournament.json"
        ).read_text()
    )
    policy = _policy_hierarchy(False, prior)
    assert policy["selected_level"] == "BAU"
    assert not any(level["promoted"] for level in policy["levels"][1:])
    assert policy["validation_opened"] is False
    assert PRIMARY_COST == 0.05


def test_development_materialization_has_no_post_treatment_estimator_features() -> None:
    frame = pd.read_parquet(DEVELOPMENT)
    allowed = {
        "recency",
        "history_segment",
        "history",
        "mens",
        "womens",
        "zip_code",
        "newbie",
        "channel",
    }
    estimator_features = set(frame.columns) - {
        "segment",
        "visit",
        "conversion",
        "spend",
        "unit_hash",
    }
    assert estimator_features == allowed
