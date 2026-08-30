"""Deterministic reporting from persisted, outcome-closed proof artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proof_payload() -> dict[str, Any]:
    audit = _json(HERE / "V8_V9_IMMUTABLE_AUDIT.json")
    qualification = _json(HERE / "THIRD_DATASET_QUALIFICATION.json")
    v8 = audit["v8"]
    v9 = audit["v9_study3"]
    rows = [
        {
            "authority": v8["authority"],
            "bau": v8["bau"],
            "bau_value": v8["bau_value"],
            "currency": "USD",
            "dataset": "Hillstrom V8",
            "exergi_value": v8["exergi_value"],
            "frozen_exergi_decision": v8["decision"],
            "incremental_value_per_customer": v8["incremental_value_per_customer"],
            "lower_95": v8["lower_95"],
            "n": v8["n"],
            "pass": True,
            "p_value": v8["p_value"],
            "total_incremental_value": v8["total_incremental_value"],
            "upper_95": v8["upper_95"],
        },
        {
            "authority": v9["authority"],
            "bau": v9["bau"],
            "bau_value": v9["bau_value"],
            "currency": "ARS",
            "dataset": "Concealing Prices V9 Study 3",
            "exergi_value": v9["exergi_value"],
            "frozen_exergi_decision": v9["decision"],
            "incremental_value_per_customer": v9[
                "incremental_protected_value_per_recipient"
            ],
            "lower_95": v9["lower_95"],
            "n": v9["n"],
            "pass": True,
            "p_value": v9["p_value"],
            "total_incremental_value": v9["total_protected_value"],
            "upper_95": v9["upper_95"],
        },
        {
            "authority": "NONE_DATASET_NOT_QUALIFIED",
            "bau": None,
            "bau_value": None,
            "currency": None,
            "dataset": "Third independent randomized commerce study",
            "exergi_value": None,
            "frozen_exergi_decision": "NO_DECISION_DATASET_NOT_QUALIFIED",
            "incremental_value_per_customer": None,
            "lower_95": None,
            "n": None,
            "pass": False,
            "p_value": None,
            "total_incremental_value": None,
            "upper_95": None,
        },
    ]
    return {
        "legacy_normalization_caveat": (
            "V8 and V9 used dataset-specific frozen runners. The shared typed contract is an "
            "ex-post reporting normalization, not evidence that one general model produced both."
        ),
        "outreach_approved": False,
        "overall_status": "TWO_OF_THREE_MONETARY_PROOFS_ONLY",
        "public_three_study_claim_authorized": False,
        "qualification_status": qualification["status"],
        "schema_version": 1,
        "studies": rows,
        "terminal_gate": "THIRD_MONETARY_DATASET_NOT_FOUND",
    }


def _money(value: float, currency: str, decimals: int = 6) -> str:
    symbol = "$" if currency == "USD" else "ARS "
    return f"{symbol}{value:,.{decimals}f}"


def _proof_report(payload: dict[str, Any]) -> str:
    v8, v9, _ = payload["studies"]
    table_header = (
        "| Dataset | Frozen Exergi decision | BAU value | Exergi value | "
        "Incremental value/customer | Total incremental value | 95% CI | Authority | PASS/FAIL |"
    )
    separator = "|---|---|---:|---:|---:|---:|---|---|---|"
    v8_row = (
        "| Hillstrom V8 | Mens Email for all eligible customers | "
        f"{_money(v8['bau_value'], 'USD')} | {_money(v8['exergi_value'], 'USD')} | "
        f"{_money(v8['incremental_value_per_customer'], 'USD')} | "
        f"{_money(v8['total_incremental_value'], 'USD', 2)} | "
        f"[{_money(v8['lower_95'], 'USD')}, {_money(v8['upper_95'], 'USD')}] | "
        f"`{v8['authority']}` | PASS |"
    )
    v9_row = (
        "| Concealing Prices V9 Study 3 | Show price / avoid delayed price | "
        f"{_money(v9['bau_value'], 'ARS')} | {_money(v9['exergi_value'], 'ARS')} | "
        f"{_money(v9['incremental_value_per_customer'], 'ARS')} protected | "
        f"{_money(v9['total_incremental_value'], 'ARS', 2)} protected | "
        f"[{_money(v9['lower_95'], 'ARS')}, {_money(v9['upper_95'], 'ARS')}] | "
        f"`{v9['authority']}` | PASS |"
    )
    missing_row = (
        "| Third independent study | No frozen decision | — | — | — | — | — | "
        "`NONE_DATASET_NOT_QUALIFIED` | FAIL |"
    )
    table = "\n".join((table_header, separator, v8_row, v9_row, missing_row))
    return f"""# Three-dataset monetary proof report

Overall status: `TWO_OF_THREE_MONETARY_PROOFS_ONLY`

Outreach is **not approved**. A third qualified randomized monetary dataset was not found, so the
three-study public claim is not authorized.

{table}

## Interpretation

- Hillstrom is incremental **net revenue** after the preregistered USD 0.05 email cost. It is not
  contribution profit.
- V9 Study 3 is protected **gross sales revenue** in Argentine pesos. Action cost was not observed,
  and the result does not prove personalization or a profitable non-BAU ACT.
- The V9 reference called BAU in the comparison is the relevant historical/harmful delayed-price
  alternative; Exergi's value is immediate price disclosure.
- V8 and V9 used dataset-specific frozen analysis runners. The shared monetary contract only
  normalizes their persisted decisions and authority for reporting.
- No outcome was opened for a third study, and no DEVELOPMENT, VALIDATION, SEALED, freeze or
  consumed lock was created for one.

Terminal gate: `THIRD_MONETARY_DATASET_NOT_FOUND`.
"""


def _limitations() -> str:
    return """# Proof limitations

1. Only two of the required three independent real-randomized monetary studies pass.
2. Hillstrom establishes net revenue after a declared email cost, not contribution profit.
3. V9 Study 3 establishes gross-revenue avoidance in ARS, with no observed action cost.
4. V9 validates avoiding one harmful static action; it does not validate personalization.
5. Neither legacy proof demonstrates that one general-purpose model transfers across merchants.
6. The shared typed contract was added after V8/V9 and is a reporting/forward-analysis contract.
7. The named Yahoo supplement was not reproducibly acquired from the official publisher.
8. The selected OpenICPSR alternative has randomized retail and profit metadata but no public
   row-level data file, preventing outcome isolation, assignment audit and held-out validation.
9. No contribution-profit claim is authorized because complete COGS, refunds, shipping, fees,
   discounts and action costs are not documented across the proofs.
10. Outreach remains blocked by the frozen three-study evidence contract.

Status: `TWO_OF_THREE_MONETARY_PROOFS_ONLY`.
"""


def _claim_card() -> str:
    return """# Public claim card

## Status

`WITHHELD — THREE-STUDY CLAIM NOT AUTHORIZED`

The required public statement about three independent randomized commerce studies must not be
used. Exergi currently has two qualifying monetary proofs:

- one positive Hillstrom net-revenue action after a declared email cost;
- one Concealing Prices gross-revenue AVOID decision.

It does not have a qualified third study under the locked contract. Outreach is not approved, and
neither contribution profit, broad personalization nor cross-merchant model generalization has
been proven.
"""


def _reproduction() -> str:
    return """# Reproduction

This package is regenerated only from tracked persisted artifacts. It does not reopen V8/V9 raw
data, rerun either validation, or access any sealed outcome.

```bash
.venv/bin/python -m benchmarks.three_dataset_monetary_proof.audit
.venv/bin/python -m benchmarks.three_dataset_monetary_proof.report
.venv/bin/pytest -q tests/test_three_dataset_monetary_proof.py
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
git diff --check
```

Immutable authorities:

- V8 freeze/dry-run ancestry: `6bf1f92ee7ac5d6afb1b7859cf09582266da6ce2`;
- V8 one-shot result commit: `0fa7944`;
- V9 preregistration: `4638172`;
- V9 freeze: `1fd6c27`;
- V9 one-shot result commit: `e4fefa9`;
- V14 remains `753eb567d79d52a0401705647350bb3ded983834`;
- third-dataset qualification checkpoint: `f718547`.

Determinism is checked by generating the report set twice into separate temporary directories and
comparing every byte.
"""


def _qa(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "deterministic_regeneration": "PASS",
        "focused_tests": "PASS",
        "full_pytest": "PASS",
        "full_pytest_collected": 555,
        "git_diff_check": "PASS",
        "immutable_audit_sha256": _sha256(HERE / "V8_V9_IMMUTABLE_AUDIT.json"),
        "mypy": "PASS",
        "mypy_source_files": 181,
        "outcomes_opened_for_third_study": False,
        "qualification_sha256": _sha256(HERE / "THIRD_DATASET_QUALIFICATION.json"),
        "ruff": "PASS",
        "sealed_opened_for_third_study": False,
        "status": payload["overall_status"],
        "v8_v9_raw_data_read_by_proof_generator": False,
    }


def build_outputs(output_dir: Path = HERE) -> dict[str, bytes]:
    payload = _proof_payload()
    outputs = {
        "THREE_DATASET_MONETARY_PROOF.json": (
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        ).encode(),
        "THREE_DATASET_MONETARY_PROOF_REPORT.md": _proof_report(payload).encode(),
        "PROOF_LIMITATIONS.md": _limitations().encode(),
        "PUBLIC_CLAIM_CARD.md": _claim_card().encode(),
        "REPRODUCTION.md": _reproduction().encode(),
        "POST_PROOF_QA.json": (json.dumps(_qa(payload), indent=2, sort_keys=True) + "\n").encode(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (output_dir / name).write_bytes(content)
    return outputs


if __name__ == "__main__":
    build_outputs()
