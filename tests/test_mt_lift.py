from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from decision_engine.benchmark.mt_lift import run_mt_lift_benchmark
from decision_engine.datasets.mt_lift import MTLiftAdapter


def _write_fixture(root: Path, rows: int = 300) -> None:
    root.mkdir()
    for split in ("train", "test"):
        treatment = [index % 5 for index in range(rows)]
        frame = pl.DataFrame(
            {
                **{f"f{index}": [(row + index) % 7 for row in range(rows)] for index in range(99)},
                "click": [int((row % 5) <= treatment[row]) for row in range(rows)],
                "conversion": [int((row % 11) <= treatment[row]) for row in range(rows)],
                "treatment": treatment,
            }
        )
        frame.write_csv(root / f"{split}.csv")


def test_mt_lift_adapter_is_strict_and_anonymized(tmp_path: Path) -> None:
    root = tmp_path / "mt_lift"
    _write_fixture(root)
    adapter = MTLiftAdapter(root)
    assert adapter.available()
    assert adapter.design.assignment == "RANDOMIZED_MULTI_ARM"
    assert adapter.design.feature_semantics == "ANONYMIZED; DO NOT INTERPRET"
    assert adapter.validate("train")["treatments"] == [0, 1, 2, 3, 4]


def test_mt_lift_missing_data_fails_closed(tmp_path: Path) -> None:
    adapter = MTLiftAdapter(tmp_path)
    assert not adapter.available()
    with pytest.raises(FileNotFoundError, match="publisher"):
        adapter.load_split("train")


def test_mt_lift_predictions_are_frozen_before_randomized_evaluation(tmp_path: Path) -> None:
    root = tmp_path / "mt_lift"
    _write_fixture(root, rows=500)
    result = run_mt_lift_benchmark(root, tmp_path / "artifacts", max_train_rows=500)
    assert result["frozen_before_outcome_evaluation"] is True
    assert result["train_rows"] == 500
    assert set(result["randomized_arm_rates"]) == {0, 1, 2, 3, 4}
    assert (tmp_path / "artifacts/frozen_predictions.parquet").exists()
