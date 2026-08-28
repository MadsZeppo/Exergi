from __future__ import annotations

from pathlib import Path

import numpy as np

from benchmarks.ecommerce_decision_layer_v7_2.hillstrom_development import (
    COST_GRID,
    DEVELOPMENT,
    PRIMARY_COST,
    _make_data,
)
from benchmarks.ecommerce_decision_layer_v7_2.materialize_hillstrom_development import (
    EXPECTED_COLUMNS,
    parse_development_lines,
)
from decision_engine.datasets.buy_baits import VariableTiming
from decision_engine.datasets.hillstrom import HILLSTROM_VARIABLE_TIMING
from decision_engine.economic_policy_v72.splits import stable_unit_hash


def test_hillstrom_feature_timing_matches_primary_source_dictionary() -> None:
    assert set(HILLSTROM_VARIABLE_TIMING) == set(EXPECTED_COLUMNS)
    for feature in (
        "recency",
        "history_segment",
        "history",
        "mens",
        "womens",
        "zip_code",
        "newbie",
        "channel",
    ):
        assert HILLSTROM_VARIABLE_TIMING[feature] is VariableTiming.PRETREATMENT_ALLOWED
    assert HILLSTROM_VARIABLE_TIMING["segment"] is VariableTiming.ASSIGNMENT_ONLY
    for outcome in ("visit", "conversion", "spend"):
        assert HILLSTROM_VARIABLE_TIMING[outcome] is VariableTiming.OUTCOME_ONLY


def test_materializer_never_decodes_nondevelopment_outcome_lines() -> None:
    header = (",".join(EXPECTED_COLUMNS) + "\n").encode()
    invalid_sealed_line = b"\xff\xfe\n"
    development_line = b"1,1) $0 - $100,50,1,0,Urban,0,Web,No E-Mail,0,0,0\n"
    development_hash = stable_unit_hash("hillstrom", "row-1")
    records = parse_development_lines(
        [header, invalid_sealed_line, development_line], {development_hash}
    )
    assert len(records) == 1
    assert records[0]["unit_hash"] == development_hash
    assert records[0]["spend"] == "0"


def test_hillstrom_cost_grid_and_contract_are_preregistered() -> None:
    assert COST_GRID == (0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 1.00, 2.00)
    assert PRIMARY_COST == 0.05
    data = _make_data(
        np.zeros((3, 2)),
        np.asarray([0, 1, 2]),
        np.asarray([0.0, 1.0, 2.0]),
        np.asarray(["a", "b", "c"]),
        0.25,
    )
    assert np.all(data.action_cost[:, 0] == 0)
    assert np.all(data.action_cost[:, 1:] == 0.25)


def test_hillstrom_runner_has_development_path_only() -> None:
    assert DEVELOPMENT.name == "development.parquet"
    source = Path(
        "benchmarks/ecommerce_decision_layer_v7_2/hillstrom_development.py"
    ).read_text()
    assert "validation.parquet" not in source
    assert "sealed_test.parquet" not in source
    assert "data/raw/hillstrom" not in source
