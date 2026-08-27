"""Runtime and source-level boundary around invalidated legacy oracle-derived priors."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from decision_engine.core.authority import ClaimAuthority


class EvidenceOrigin(StrEnum):
    LOCAL_RANDOMIZED_OUTCOMES = "LOCAL_RANDOMIZED_OUTCOMES"
    EXTERNAL_RANDOMIZED_OUTCOMES = "EXTERNAL_RANDOMIZED_OUTCOMES"
    OBSERVATIONAL = "OBSERVATIONAL"
    SYNTHETIC_OBSERVED_RANDOMIZATION = "SYNTHETIC_OBSERVED_RANDOMIZATION"
    EVALUATOR_ONLY_ORACLE = "EVALUATOR_ONLY_ORACLE"
    LEGACY_ORACLE_DERIVED_PRIOR = "LEGACY_ORACLE_DERIVED_PRIOR"


@dataclass(frozen=True)
class EvidenceProvenance:
    evidence_id: str
    origin: EvidenceOrigin
    authority: ClaimAuthority
    randomized_assignment: bool
    oracle_derived: bool = False
    evaluation_only: bool = False
    source_module: str = ""


@dataclass(frozen=True)
class V71PolicyEvidence:
    records: tuple[EvidenceProvenance, ...]

    def __post_init__(self) -> None:
        assert_policy_safe(self.records)


FORBIDDEN_POLICY_ORIGINS = {
    EvidenceOrigin.EVALUATOR_ONLY_ORACLE,
    EvidenceOrigin.LEGACY_ORACLE_DERIVED_PRIOR,
}
FORBIDDEN_IMPORT_PREFIXES = (
    "benchmarks.ecommerce_decision_layer_v6",
    "benchmarks.ecommerce_decision_layer_v6_1",
    "benchmarks.ecommerce_decision_layer_v6_2",
)
FORBIDDEN_POLICY_SYMBOLS = {
    "build_source_records",
    "_source_prior",
    "oracle_family_values",
}


def assert_policy_safe(records: tuple[EvidenceProvenance, ...]) -> None:
    for record in records:
        if record.origin in FORBIDDEN_POLICY_ORIGINS:
            raise PermissionError(f"quarantined evidence origin: {record.origin}")
        if record.oracle_derived or record.evaluation_only:
            raise PermissionError(
                f"oracle/evaluator evidence cannot enter policy: {record.evidence_id}"
            )
        if record.source_module.startswith(FORBIDDEN_IMPORT_PREFIXES):
            raise PermissionError(f"legacy V6 module is quarantined: {record.source_module}")


def scan_policy_source(paths: tuple[Path, ...]) -> tuple[str, ...]:
    """Return explicit import/call violations without importing quarantined modules."""

    violations: list[str] = []
    for path in paths:
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                        violations.append(f"{path}:{node.lineno}: forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(f"{path}:{node.lineno}: forbidden import {module}")
                for alias in node.names:
                    if alias.name in FORBIDDEN_POLICY_SYMBOLS:
                        violations.append(f"{path}:{node.lineno}: forbidden symbol {alias.name}")
            elif isinstance(node, ast.Name) and node.id in FORBIDDEN_POLICY_SYMBOLS:
                violations.append(f"{path}:{node.lineno}: forbidden symbol {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_POLICY_SYMBOLS:
                violations.append(f"{path}:{node.lineno}: forbidden symbol {node.attr}")
    return tuple(sorted(set(violations)))
