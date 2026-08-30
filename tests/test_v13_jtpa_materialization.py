from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.materialize import (
    OUTCOME_BYTES,
    RECORD_BYTES,
    development_frame,
    read_selected_outcomes,
)


def _record(value: float, recid: str) -> bytes:
    outcomes = struct.pack("<30f", *([value] * 30))
    return outcomes + recid.encode().ljust(6, b" ") + b"\0" * (RECORD_BYTES - OUTCOME_BYTES - 6)


def test_v13_row_addressed_reader_reads_only_selected_outcomes(tmp_path: Path) -> None:
    path = tmp_path / "fixed.dta"
    header = b"H" * 17
    path.write_bytes(header + _record(1.0, "000001") + _record(999.0, "000002"))
    frame, audit = read_selected_outcomes(
        path,
        {"000001"},
        nobs=2,
        data_offset=len(header),
    )
    assert frame["recid"].tolist() == ["000001"]
    assert frame["earnings_30m"].tolist() == [30.0]
    assert audit["outcome_rows_read"] == 1
    assert audit["id_bytes_read_for_all_source_rows"] == 12


def test_v13_development_materialization_excludes_validation_outcomes() -> None:
    frame, access = development_frame()
    assert len(frame) == access["development_ids"] == 9_025
    assert access["validation_ids"] == 6_109
    assert access["validation_outcome_bytes_opened"] == 0
    assert access["validation_outcomes_opened"] is False
    assert np.isfinite(frame["earnings_30m"]).all()
    assert (frame["earnings_30m"] >= 0).all()


def test_v13_assignment_is_binary_after_development_join() -> None:
    frame, _ = development_frame()
    assert set(frame["treatment"]) == {0, 1}
    assert frame["recid"].is_unique
