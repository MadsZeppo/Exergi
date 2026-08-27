from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from commercial_twin.customer_twin_core import (
    ActionDefinition,
    ActionFamily,
    EvidenceBoundAnswerRenderer,
    EvidenceType,
    action_evidence_for_dataset,
)
from decision_engine.causal.dunnhumby_backtest import (
    FEATURES,
    deterministic_aa,
    fit_and_freeze,
    preregistered_split,
)
from decision_engine.causal.layer3_validation import cross_fitted_aipw, generate_synthetic_uplift
from decision_engine.datasets.dunnhumby import DunnhumbyDataset


def test_synthetic_randomized_recovers_known_effect() -> None:
    data = generate_synthetic_uplift(seed=42, scenario="randomized")
    result = cross_fitted_aipw(data.features, data.treatment, data.outcome, data.segment, seed=42)
    assert abs(result.ate - data.true_effect.mean()) < 0.015
    assert result.overlap_fraction > 0.99


def test_synthetic_confounding_bias_is_reduced() -> None:
    data = generate_synthetic_uplift(seed=42, scenario="confounded")
    result = cross_fitted_aipw(data.features, data.treatment, data.outcome, data.segment, seed=42)
    truth = float(data.true_effect.mean())
    assert abs(result.naive_ate - truth) > 0.05
    assert abs(result.ate - truth) < abs(result.naive_ate - truth)
    assert result.fraction_clipped >= 0


def test_synthetic_placebo_interval_contains_zero() -> None:
    data = generate_synthetic_uplift(seed=42, scenario="placebo")
    result = cross_fitted_aipw(data.features, data.treatment, data.outcome, data.segment, seed=42)
    assert result.lower <= 0 <= result.upper


def test_synthetic_interval_coverage_fixture() -> None:
    covered = []
    for seed in range(12):
        data = generate_synthetic_uplift(seed=seed, n_customers=6_000, scenario="randomized")
        result = cross_fitted_aipw(
            data.features, data.treatment, data.outcome, data.segment, seed=seed
        )
        truth = float(data.true_effect.mean())
        covered.append(result.lower <= truth <= result.upper)
    assert np.mean(covered) >= 0.75


def test_dunnhumby_missing_files_fail_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="authorized"):
        DunnhumbyDataset(tmp_path).resolve_files()


def _write_fixture_files(directory: Path) -> None:
    fixtures = {
        "transaction_data.csv": {
            "HOUSEHOLD_KEY": [1],
            "BASKET_ID": [10],
            "DAY": [1],
            "PRODUCT_ID": [100],
            "QUANTITY": [1],
            "SALES_VALUE": [2.5],
            "RETAIL_DISC": [0.0],
            "COUPON_DISC": [0.0],
        },
        "product.csv": {"PRODUCT_ID": [100]},
        "campaign_table.csv": {"HOUSEHOLD_KEY": [1], "CAMPAIGN": [7]},
        "campaign_desc.csv": {"CAMPAIGN": [7], "START_DAY": [1], "END_DAY": [5]},
        "coupon.csv": {"COUPON_UPC": [9], "PRODUCT_ID": [100], "CAMPAIGN": [7]},
        "coupon_redempt.csv": {
            "HOUSEHOLD_KEY": [1],
            "COUPON_UPC": [9],
            "CAMPAIGN": [7],
            "REDEMPTION_DATE": [3],
        },
    }
    for name, values in fixtures.items():
        pl.DataFrame(values).write_csv(directory / name)


def test_dunnhumby_ingestion_writes_hashes_schema_and_mapping(tmp_path: Path) -> None:
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    _write_fixture_files(raw)
    provenance = DunnhumbyDataset(raw).prepare(
        processed, source="licensed local fixture", license_terms="fixture terms"
    )
    persisted = json.loads((processed / "provenance.json").read_text())
    assert provenance["files"]["transaction_data"]["rows"] == 1
    assert len(persisted["files"]["transaction_data"]["sha256"]) == 64
    assert "HOUSEHOLD_KEY" in persisted["observed_fields"]["transaction_data"]
    assert "redemption is not assignment" in persisted["canonical_mapping"]["coupon+coupon_redempt"]


def test_observational_wording_and_online_retail_fail_closed() -> None:
    renderer = EvidenceBoundAnswerRenderer()
    observational = renderer.render_statement(
        EvidenceType.CAUSAL_OBSERVATIONAL, "campaign exposure changed purchase probability"
    )
    insufficient = renderer.render_statement(EvidenceType.INSUFFICIENT, "discount effect")
    assert "identification assumptions" in observational
    assert "not have enough evidence" in insufficient


def test_same_action_contract_distinguishes_assignment_support() -> None:
    action = ActionDefinition(action_id="campaign-x", family=ActionFamily.TARGETED_COMMUNICATION)
    online_retail = action_evidence_for_dataset(
        "Online Retail II",
        action,
        assignment_observed=False,
        overlap_valid=False,
        frozen_backtest_available=False,
    )
    dunnhumby_ready = action_evidence_for_dataset(
        "Dunnhumby Complete Journey",
        action,
        assignment_observed=True,
        overlap_valid=True,
        frozen_backtest_available=True,
    )
    assert online_retail.evidence_type == EvidenceType.INSUFFICIENT
    assert dunnhumby_ready.evidence_type == EvidenceType.CAUSAL_OBSERVATIONAL
    assert dunnhumby_ready.evidence_type != EvidenceType.CAUSAL_RCT


def test_dunnhumby_preregistered_temporal_split_is_deterministic() -> None:
    descriptions = pl.DataFrame(
        {
            "campaign_id": [str(index) for index in range(10)],
            "start_date": [datetime(2017, month, 1) for month in range(1, 11)],
            "end_date": [datetime(2017, month, 5) for month in range(1, 11)],
        }
    ).to_pandas()
    cutoff, development, backtest = preregistered_split(
        descriptions, datetime(2016, 12, 1), datetime(2017, 12, 31)
    )
    assert cutoff == datetime(2017, 8, 1)
    assert max(development["start_date"]) < cutoff
    assert min(backtest["start_date"]) >= cutoff


def test_dunnhumby_frozen_nuisances_are_deterministic() -> None:
    rng = np.random.default_rng(42)
    size = 500
    development = pl.DataFrame(
        {
            **{name: rng.normal(size=size) for name in FEATURES},
            "treatment": rng.binomial(1, 0.5, size),
        }
    ).to_pandas()
    development_outcome = rng.binomial(1, 1 / (1 + np.exp(-development["recency_days"].to_numpy())))
    final = pl.DataFrame(
        {
            **{name: rng.normal(size=size) for name in FEATURES},
            "treatment": rng.binomial(1, 0.5, size),
        }
    ).to_pandas()
    first = fit_and_freeze(
        development,
        development_outcome,
        final,
        campaign_id="18",
        start_date=datetime(2017, 10, 30),
    )
    second = fit_and_freeze(
        development,
        development_outcome,
        final,
        campaign_id="18",
        start_date=datetime(2017, 10, 30),
    )
    assert np.array_equal(first.propensity, second.propensity)
    assert np.array_equal(first.predicted_uplift, second.predicted_uplift)
    assert np.isfinite(first.propensity).all()


def test_dunnhumby_aa_is_deterministic() -> None:
    ids = [str(index) for index in range(1_000)]
    treatment = np.ones(1_000, dtype=int)
    outcome = np.tile([0, 1], 500)
    assert deterministic_aa(ids, outcome, treatment) == deterministic_aa(ids, outcome, treatment)
