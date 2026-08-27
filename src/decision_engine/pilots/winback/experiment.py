"""Eligibility, immutable contract freezing and deterministic stratified assignment."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import (
    AssignmentRecord,
    CampaignEligibilityRecord,
    WinbackExperimentContract,
)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def eligible_cohort(
    records: list[CampaignEligibilityRecord],
    *,
    snapshot_at: datetime,
    inactivity_days: int,
    minimum_purchases: int,
    parallel_campaign_exclusion_days: int,
) -> tuple[str, ...]:
    if snapshot_at.tzinfo is None:
        raise ValueError("snapshot_at must be timezone-aware")
    inactivity_cutoff = snapshot_at - timedelta(days=inactivity_days)
    campaign_cutoff = snapshot_at - timedelta(days=parallel_campaign_exclusion_days)
    selected = []
    for row in records:
        valid = (
            row.snapshot_at == snapshot_at
            and row.consent
            and not row.suppressed
            and row.historical_purchase_count >= minimum_purchases
            and row.last_purchase_at is not None
            and row.last_purchase_at <= inactivity_cutoff
            and (
                row.last_parallel_campaign_at is None
                or row.last_parallel_campaign_at <= campaign_cutoff
            )
        )
        if valid:
            selected.append(row.customer_id)
    if len(selected) != len(set(selected)):
        raise ValueError("eligibility snapshot contains duplicate customer IDs")
    return tuple(sorted(selected))


def freeze_contract(
    contract: WinbackExperimentContract,
    *,
    eligible_customer_ids: tuple[str, ...],
    frozen_at: datetime,
) -> WinbackExperimentContract:
    if frozen_at.tzinfo is None:
        raise ValueError("frozen_at must be timezone-aware")
    cohort_hash = stable_hash(eligible_customer_ids)
    if cohort_hash != contract.eligibility_hash:
        raise ValueError("eligible cohort does not match preregistered eligibility hash")
    if len(eligible_customer_ids) < contract.planned_sample_size:
        raise ValueError("eligible cohort is smaller than the frozen planned sample size")
    if contract.frozen_at is not None:
        expected = stable_hash(contract.model_dump(mode="json", exclude={"contract_hash"}))
        if expected != contract.contract_hash:
            raise ValueError("frozen experiment contract hash is invalid")
        return contract
    provisional = contract.model_copy(update={"frozen_at": frozen_at})
    digest = stable_hash(provisional.model_dump(mode="json", exclude={"contract_hash"}))
    return provisional.model_copy(update={"contract_hash": digest})


def assign_cohort(
    contract: WinbackExperimentContract,
    *,
    eligible_customer_ids: tuple[str, ...],
    assigned_at: datetime,
    strata: dict[str, str] | None = None,
) -> tuple[AssignmentRecord, ...]:
    if contract.frozen_at is None or contract.contract_hash is None:
        raise RuntimeError("experiment contract must be frozen before assignment")
    if assigned_at.tzinfo is None or assigned_at < contract.frozen_at:
        raise ValueError("assignment must be timezone-aware and follow contract freeze")
    if stable_hash(tuple(sorted(eligible_customer_ids))) != contract.eligibility_hash:
        raise ValueError("assignment cohort differs from the frozen eligibility cohort")
    strata = strata or {customer_id: "ALL" for customer_id in eligible_customer_ids}
    if set(strata) != set(eligible_customer_ids):
        raise ValueError("strata must cover the frozen eligible cohort exactly")
    grouped: dict[str, list[str]] = defaultdict(list)
    for customer_id in eligible_customer_ids:
        grouped[strata[customer_id]].append(customer_id)
    output: list[AssignmentRecord] = []
    for stratum, customers in sorted(grouped.items()):
        ordered = sorted(
            customers,
            key=lambda customer_id: hmac.new(
                contract.randomization_seed.encode(),
                f"{contract.experiment_id}|{stratum}|{customer_id}".encode(),
                hashlib.sha256,
            ).digest(),
        )
        cumulative = 0.0
        boundaries: list[int] = []
        for arm in contract.arms[:-1]:
            cumulative += arm.allocation_probability
            boundaries.append(round(cumulative * len(ordered)))
        starts = [0, *boundaries]
        ends = [*boundaries, len(ordered)]
        for arm, start, end in zip(contract.arms, starts, ends, strict=True):
            for customer_id in ordered[start:end]:
                payload = {
                    "experiment_id": contract.experiment_id,
                    "customer_id": customer_id,
                    "stratum": stratum,
                    "arm": arm.name,
                    "propensity": arm.allocation_probability,
                    "assigned_at": assigned_at.isoformat(),
                    "contract_hash": contract.contract_hash,
                }
                output.append(
                    AssignmentRecord(
                        experiment_id=contract.experiment_id,
                        merchant_id=contract.merchant_id,
                        customer_id=customer_id,
                        stratum=stratum,
                        arm=arm.name,
                        propensity=arm.allocation_probability,
                        assigned_at=assigned_at,
                        contract_hash=contract.contract_hash,
                        assignment_hash=stable_hash(payload),
                    )
                )
    return tuple(sorted(output, key=lambda row: row.customer_id))


def export_assignments_idempotent(rows: tuple[AssignmentRecord, ...], path: Path) -> str:
    lines = [
        "experiment_id,merchant_id,customer_id,stratum,arm,propensity,assigned_at,"
        "contract_hash,assignment_hash"
    ]
    for row in rows:
        lines.append(
            ",".join(
                (
                    row.experiment_id,
                    row.merchant_id,
                    row.customer_id,
                    row.stratum,
                    row.arm,
                    str(row.propensity),
                    row.assigned_at.isoformat(),
                    row.contract_hash,
                    row.assignment_hash,
                )
            )
        )
    encoded = "\n".join(lines) + "\n"
    if path.exists() and path.read_text() != encoded:
        raise RuntimeError("immutable assignment export already exists with different content")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded)
    return hashlib.sha256(encoded.encode()).hexdigest()
