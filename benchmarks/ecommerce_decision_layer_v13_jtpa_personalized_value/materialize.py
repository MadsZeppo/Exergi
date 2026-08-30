from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd

from .qualification import BASELINE, OUTCOME_SCHEMA, ROOT, sha256
from .split import split_ids

SCALEDUI = OUTCOME_SCHEMA / "analysis" / "scaledui.dta"
DATA_OFFSET = 3_876
NOBS = 16_004
MONTHS = 30
OUTCOME_BYTES = MONTHS * 4
RECID_BYTES = 6
RECORD_BYTES = OUTCOME_BYTES + RECID_BYTES + 8
DEVELOPMENT_ACCESS = ROOT / "manifests" / "V13_DEVELOPMENT_ACCESS.json"


def _read_exact(handle: BinaryIO, offset: int, size: int) -> bytes:
    handle.seek(offset)
    value = handle.read(size)
    if len(value) != size:
        raise RuntimeError(f"short V13 Stata read at byte {offset}")
    return value


def row_id(handle: BinaryIO, row: int, *, data_offset: int = DATA_OFFSET) -> str:
    offset = data_offset + row * RECORD_BYTES + OUTCOME_BYTES
    return _read_exact(handle, offset, RECID_BYTES).decode("latin-1").strip()


def read_selected_outcomes(
    path: Path,
    selected_ids: set[str],
    *,
    nobs: int = NOBS,
    data_offset: int = DATA_OFFSET,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Read only selected fixed-width outcome records; all other rows expose RECID bytes only."""
    selected_rows: list[tuple[int, str]] = []
    observed_ids: set[str] = set()
    with path.open("rb") as handle:
        for row in range(nobs):
            recid = row_id(handle, row, data_offset=data_offset)
            if not recid or recid in observed_ids:
                raise RuntimeError("invalid or duplicate RECID in SCALEDUI")
            observed_ids.add(recid)
            if recid in selected_ids:
                selected_rows.append((row, recid))

        matrix = np.empty((len(selected_rows), MONTHS), dtype=np.float64)
        for output_row, (source_row, _) in enumerate(selected_rows):
            raw = _read_exact(
                handle,
                data_offset + source_row * RECORD_BYTES,
                OUTCOME_BYTES,
            )
            matrix[output_row] = np.asarray(struct.unpack("<30f", raw), dtype=np.float64)

    found_ids = {recid for _, recid in selected_rows}
    if found_ids != selected_ids:
        missing = sorted(selected_ids - found_ids)
        raise RuntimeError(f"selected V13 IDs absent from SCALEDUI: {missing[:3]}")
    if np.any(~np.isfinite(matrix)) or np.any(matrix > 1e30):
        raise RuntimeError("missing/nonfinite monthly outcome in frozen V13 population")
    if np.any(matrix < 0):
        raise RuntimeError("negative monthly earnings in V13 SCALEDUI")

    columns = [f"uiern{month:02d}" for month in range(1, MONTHS + 1)]
    frame = pd.DataFrame(matrix, columns=columns)
    frame.insert(0, "recid", [recid for _, recid in selected_rows])
    frame["earnings_30m"] = matrix.sum(axis=1)
    audit = {
        "data_offset": data_offset,
        "file_sha256": sha256(path),
        "id_bytes_read_for_all_source_rows": nobs * RECID_BYTES,
        "outcome_bytes_per_selected_row": OUTCOME_BYTES,
        "outcome_rows_read": len(selected_rows),
        "record_bytes": RECORD_BYTES,
        "selected_id_hash": hashlib.sha256(
            "\n".join(sorted(selected_ids)).encode()
        ).hexdigest(),
        "source_rows": nobs,
    }
    return frame, audit


def development_frame() -> tuple[pd.DataFrame, dict[str, object]]:
    development_ids, validation_ids = split_ids()
    outcomes, read_audit = read_selected_outcomes(SCALEDUI, development_ids)
    baseline = pd.read_stata(BASELINE, convert_categoricals=False)
    baseline["recid"] = baseline["recid"].astype(str).str.strip()
    selected = baseline[baseline["recid"].isin(development_ids)].copy()
    frame = selected.merge(outcomes, on="recid", how="inner", validate="one_to_one")
    if len(frame) != len(development_ids):
        raise RuntimeError("V13 development baseline/outcome join failed")
    if set(frame["recid"]) & validation_ids:
        raise RuntimeError("V13 validation participant entered development materialization")
    frame["treatment"] = (frame["ra_stat"] == "1").astype(np.int8)
    access = {
        "development_ids": len(development_ids),
        "development_outcome_rows_opened": len(outcomes),
        "read_audit": read_audit,
        "schema_version": 1,
        "source_preregistration_commit": "54853cf7db0f2d0fe45f3a421be230ed3f4ce10f",
        "validation_ids": len(validation_ids),
        "validation_outcome_bytes_opened": 0,
        "validation_outcomes_opened": False,
    }
    return frame, access


def materialize_development_access_record() -> dict[str, object]:
    _, access = development_frame()
    DEVELOPMENT_ACCESS.write_text(
        json.dumps(access, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return access


if __name__ == "__main__":
    materialize_development_access_record()
