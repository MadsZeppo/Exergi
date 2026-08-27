from __future__ import annotations

from pathlib import Path

import pytest

from decision_engine.core.authority import ClaimAuthority
from decision_engine.safety.legacy_oracle_quarantine import (
    EvidenceOrigin,
    EvidenceProvenance,
    V71PolicyEvidence,
    scan_policy_source,
)

ROOT = Path(__file__).resolve().parents[1]


def _record(**changes: object) -> EvidenceProvenance:
    values: dict[str, object] = {
        "evidence_id": "safe-rct",
        "origin": EvidenceOrigin.LOCAL_RANDOMIZED_OUTCOMES,
        "authority": ClaimAuthority.REAL_RANDOMIZED_CONTRIBUTION_PROFIT,
        "randomized_assignment": True,
        "oracle_derived": False,
        "evaluation_only": False,
        "source_module": "commercial_twin.merchant_validation.rct_protocol",
    }
    values.update(changes)
    return EvidenceProvenance(**values)


def test_safe_randomized_evidence_enters_v71_policy() -> None:
    context = V71PolicyEvidence((_record(),))
    assert context.records[0].evidence_id == "safe-rct"


@pytest.mark.parametrize(
    "record",
    [
        _record(origin=EvidenceOrigin.LEGACY_ORACLE_DERIVED_PRIOR),
        _record(origin=EvidenceOrigin.EVALUATOR_ONLY_ORACLE, evaluation_only=True),
        _record(oracle_derived=True),
        _record(source_module="benchmarks.ecommerce_decision_layer_v6.simulator"),
    ],
)
def test_legacy_oracle_evidence_is_rejected_at_runtime(record: EvidenceProvenance) -> None:
    with pytest.raises(PermissionError):
        V71PolicyEvidence((record,))


def test_v71_policy_source_has_no_legacy_import_or_call_path() -> None:
    policy_paths = tuple((ROOT / "src/decision_engine").rglob("*.py"))
    assert scan_policy_source(policy_paths) == ()


def test_scanner_detects_forbidden_import_and_symbol(tmp_path: Path) -> None:
    path = tmp_path / "invalid.py"
    path.write_text(
        "from benchmarks.ecommerce_decision_layer_v6.simulator import build_source_records\n"
    )
    violations = scan_policy_source((path,))
    assert any("forbidden import" in violation for violation in violations)
    assert any("forbidden symbol" in violation for violation in violations)

