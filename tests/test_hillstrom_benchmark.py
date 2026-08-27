import numpy as np
import polars as pl
import pytest

from decision_engine.benchmark.hillstrom import (
    bootstrap_effect,
    dr_value,
    ipw_value,
    stratified_rct_split,
)
from decision_engine.datasets.hillstrom import CONTROL, MENS, WOMENS, HillstromDataset


def test_actual_hillstrom_treatments_and_features() -> None:
    frame = HillstromDataset("data/raw/hillstrom/hillstrom.csv").load_rct()
    assert set(frame["treatment"].unique()) == {CONTROL, MENS, WOMENS}
    assert frame.height == 64_000
    features = HillstromDataset.feature_columns(frame)
    assert set(features) == {
        "recency",
        "history_segment",
        "history",
        "mens",
        "womens",
        "zip_code",
        "newbie",
        "channel",
    }


def test_post_treatment_feature_audit() -> None:
    with pytest.raises(AssertionError, match="post-treatment"):
        HillstromDataset.assert_pre_treatment_features(["history", "spend"])


def test_stratified_split_is_deterministic_and_disjoint() -> None:
    treatment = np.resize(np.array([CONTROL, MENS, WOMENS]), 300)
    first = stratified_rct_split(treatment, 42)
    second = stratified_rct_split(treatment, 42)
    assert all(np.array_equal(a, b) for a, b in zip(first, second, strict=True))
    assert [part.size for part in first] == [180, 60, 60]
    assert not set(first[0]) & set(first[1]) & set(first[2])


def test_difference_and_bootstrap_are_correct_and_deterministic() -> None:
    treatment = np.array([CONTROL, CONTROL, MENS, MENS])
    outcome = np.array([1.0, 3.0, 5.0, 7.0])
    first = bootstrap_effect(outcome, treatment, MENS, iterations=100, seed=7)
    second = bootstrap_effect(outcome, treatment, MENS, iterations=100, seed=7)
    assert first.ate == 4
    assert first == second


def test_ipw_and_dr_policy_value_on_known_rct() -> None:
    treatment = np.resize(np.array([CONTROL, MENS]), 1000)
    outcome = np.where(treatment == MENS, 3.0, 1.0)
    policy = np.full(1000, MENS)
    propensity = {CONTROL: 0.5, MENS: 0.5}
    predicted = np.column_stack([np.ones(1000), np.full(1000, 3.0), np.zeros(1000)])
    assert ipw_value(policy, treatment, outcome, propensity) == 3
    assert dr_value(policy, treatment, outcome, predicted, propensity) == 3


def test_treatment_parser_handles_capitalization(tmp_path) -> None:
    path = tmp_path / "hillstrom.csv"
    pl.DataFrame(
        {
            "Segment": ["No E-Mail", "Mens E-Mail", "Womens E-Mail"],
            "Spend": [0, 1, 2],
            "Conversion": [0, 1, 1],
            "Visit": [0, 1, 1],
            "Recency": [1, 2, 3],
        }
    ).write_csv(path)
    assert HillstromDataset(path).load_rct()["treatment"].to_list() == [CONTROL, MENS, WOMENS]
