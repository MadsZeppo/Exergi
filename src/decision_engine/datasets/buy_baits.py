"""Fail-closed adapter for the official Buy Baits V1 randomized field experiment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import pandas as pd

from decision_engine.economic_policy_v72.contracts import EconomicPolicyDataset
from decision_engine.economic_policy_v72.splits import stable_unit_hash

DATA_COLUMNS = (
    "id",
    "date",
    "treatment",
    "purchase",
    "red",
    "purchasevalue",
    "profit",
    "counting",
    "device",
    "sessions",
    "out_num90",
    "income_cat",
)


class VariableTiming(StrEnum):
    PRETREATMENT_ALLOWED = "PRETREATMENT_ALLOWED"
    ASSIGNMENT_ONLY = "ASSIGNMENT_ONLY"
    POST_TREATMENT_FORBIDDEN_FEATURE = "POST_TREATMENT_FORBIDDEN_FEATURE"
    OUTCOME_ONLY = "OUTCOME_ONLY"
    EVALUATOR_ONLY = "EVALUATOR_ONLY"
    UNKNOWN_FORBIDDEN = "UNKNOWN_FORBIDDEN"


class GovernanceStatus(StrEnum):
    ALLOWED = "ALLOWED"
    RESTRICTED = "RESTRICTED"
    PROHIBITED = "PROHIBITED"


VARIABLE_TIMING: dict[str, VariableTiming] = {
    "id": VariableTiming.EVALUATOR_ONLY,
    "date": VariableTiming.ASSIGNMENT_ONLY,
    "treatment": VariableTiming.ASSIGNMENT_ONLY,
    "purchase": VariableTiming.OUTCOME_ONLY,
    "red": VariableTiming.OUTCOME_ONLY,
    "purchasevalue": VariableTiming.OUTCOME_ONLY,
    "profit": VariableTiming.OUTCOME_ONLY,
    "counting": VariableTiming.POST_TREATMENT_FORBIDDEN_FEATURE,
    "device": VariableTiming.PRETREATMENT_ALLOWED,
    "sessions": VariableTiming.POST_TREATMENT_FORBIDDEN_FEATURE,
    "out_num90": VariableTiming.UNKNOWN_FORBIDDEN,
    "income_cat": VariableTiming.UNKNOWN_FORBIDDEN,
}

TREATMENT_LABELS = {
    1: "A: 10% automatic rebate",
    2: "B1: 10% claim, no reminder",
    3: "B2a: 10% claim, unannounced reminder",
    4: "B2b: 10% claim, announced reminder",
    5: "C1: 15% claim, no reminder",
    6: "C2a: 15% claim, unannounced reminder",
    7: "C2b: 15% claim, announced reminder",
    8: "D: control",
}

# This rule is frozen from treatment mechanics, before policy-value estimation.
ACTION_GOVERNANCE = {
    1: GovernanceStatus.ALLOWED,
    2: GovernanceStatus.PROHIBITED,
    3: GovernanceStatus.RESTRICTED,
    4: GovernanceStatus.ALLOWED,
    5: GovernanceStatus.PROHIBITED,
    6: GovernanceStatus.RESTRICTED,
    7: GovernanceStatus.ALLOWED,
    8: GovernanceStatus.ALLOWED,
}
SCIENTIFIC_ALL_ARMS = tuple(TREATMENT_LABELS)
ENTERPRISE_ALLOWED_ARMS = tuple(
    arm for arm, status in ACTION_GOVERNANCE.items() if status is GovernanceStatus.ALLOWED
)


@dataclass(frozen=True)
class BuyBaitsAssignment:
    unit_id: np.ndarray
    treatment: np.ndarray


def read_assignment_only(path: Path) -> BuyBaitsAssignment:
    """Read no outcomes; used for immutable manifests and count-only reporting."""
    frame = pd.read_stata(
        path,
        columns=["id", "treatment"],
        convert_categoricals=False,
        preserve_dtypes=False,
    )
    if frame.groupby("id")["treatment"].nunique().gt(1).any():
        raise ValueError("a randomized cookie appears in multiple treatment arms")
    frame = frame.drop_duplicates("id")
    return BuyBaitsAssignment(
        frame["id"].astype("int64").astype(str).to_numpy(),
        frame["treatment"].astype("int64").to_numpy(),
    )


def development_frame_from_audit(
    audited_frame: pd.DataFrame, development_hashes: set[str]
) -> pd.DataFrame:
    """Materialize only development rows after the one-off forensic audit."""
    if tuple(audited_frame.columns) != DATA_COLUMNS:
        raise ValueError("unexpected Buy Baits schema")
    unit_hash = audited_frame["id"].astype("int64").astype(str).map(
        lambda value: stable_unit_hash("buy_baits_v1", value)
    )
    selected = audited_frame.loc[unit_hash.isin(development_hashes)].copy()
    selected["unit_hash"] = unit_hash.loc[selected.index]
    if not set(selected["unit_hash"]).issubset(development_hashes):
        raise RuntimeError("non-development unit entered development materialization")
    return selected.drop(columns=["id"])


def policy_dataset_from_development(frame: pd.DataFrame) -> EconomicPolicyDataset:
    """Build one mature row per randomized cookie using only pre-treatment device."""
    required = (set(DATA_COLUMNS) - {"id"}) | {"unit_hash"}
    if not required.issubset(frame.columns):
        raise ValueError("development frame is missing audited columns")
    if frame.groupby("unit_hash")["treatment"].nunique().gt(1).any():
        raise ValueError("treatment contamination within randomized unit")

    working = frame.copy()
    working["profit_complete"] = working["profit"]
    working.loc[working["purchase"].eq(0), "profit_complete"] = 0.0
    incomplete = working["purchase"].eq(1) & working["profit_complete"].isna()
    incomplete_units = set(working.loc[incomplete, "unit_hash"])
    working = working.loc[~working["unit_hash"].isin(incomplete_units)]

    aggregate = working.groupby("unit_hash", sort=True).agg(
        treatment=("treatment", "first"),
        device=("device", "first"),
        monetary_outcome=("profit_complete", "sum"),
    )
    devices = ("desktop", "mobile", "tablet")
    features = np.column_stack(
        [(aggregate["device"].astype(str) == device).astype(float) for device in devices]
    )
    action = aggregate["treatment"].astype("int64").to_numpy() - 1
    n, arms = len(aggregate), 8
    propensity = np.full((n, arms), 1.0 / arms)
    costs = np.zeros((n, arms))
    allowed = np.asarray(
        np.tile(
            np.asarray(
                [arm in ENTERPRISE_ALLOWED_ARMS for arm in range(1, arms + 1)], dtype=bool
            ),
            (n, 1),
        ),
        dtype=bool,
    )
    return EconomicPolicyDataset(
        features=np.asarray(features, dtype=float),
        action=np.asarray(action, dtype=np.int64),
        monetary_outcome=aggregate["monetary_outcome"].to_numpy(dtype=float),
        propensity=propensity,
        action_cost=costs,
        allowed_actions=allowed,
        unit_id=aggregate.index.to_numpy(dtype=str),
        bau_action=7,
        mature=np.ones(n, dtype=bool),
        feature_names=tuple(f"device={device}" for device in devices),
    )
