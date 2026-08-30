"""Shared contracts for frozen randomized monetary decisions.

The module normalizes what a study must declare.  It does not pretend that the
legacy V8 and V9 runners shared one model implementation; their persisted
artifacts are adapted to this contract only for comparable reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MonetaryAuthority(StrEnum):
    GROSS_REVENUE = "REAL_RANDOMIZED_GROSS_REVENUE"
    NET_REVENUE_DECLARED_COST = "REAL_RANDOMIZED_NET_REVENUE_AFTER_DECLARED_ACTION_COST"
    CONTRIBUTION_PROFIT = "REAL_RANDOMIZED_CONTRIBUTION_PROFIT"


class CostAuthority(StrEnum):
    NONE_OBSERVED = "NO_ACTION_COST_OBSERVED"
    DECLARED_LOCKED = "DECLARED_AND_LOCKED_BEFORE_VALIDATION"
    OBSERVED = "OBSERVED_ACTION_COST"


class PolicyLevel(StrEnum):
    BAU = "BAU"
    BEST_STATIC = "BEST_STATIC"
    SEGMENT = "SIMPLE_PREREGISTERED_SEGMENT"
    PERSONALIZED = "PERSONALIZED"


class DecisionDisposition(StrEnum):
    ACT = "ACT"
    AVOID = "AVOID"
    BAU = "BAU"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"


@dataclass(frozen=True)
class RandomizedAction:
    name: str
    is_bau: bool
    propensity: float | None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("action name must be non-empty")
        if self.propensity is not None and not 0.0 < self.propensity < 1.0:
            raise ValueError("known propensity must be strictly between zero and one")


@dataclass(frozen=True)
class MonetaryDecisionContract:
    study_id: str
    randomized_unit: str
    actions: tuple[RandomizedAction, ...]
    assignment_field: str
    propensity_authority: str
    pretreatment_features: tuple[str, ...]
    monetary_outcome: str
    currency: str
    action_cost: str
    cost_authority: CostAuthority
    maturity_rule: str
    eligible_population: str
    claim_authority: MonetaryAuthority
    profit_components_documented: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.actions) < 2:
            raise ValueError("at least BAU and one challenger action are required")
        if sum(action.is_bau for action in self.actions) != 1:
            raise ValueError("exactly one action must be BAU")
        action_names = [action.name for action in self.actions]
        if len(set(action_names)) != len(action_names):
            raise ValueError("action names must be unique")
        known = [action.propensity for action in self.actions]
        if all(value is not None for value in known):
            total = sum(value for value in known if value is not None)
            if abs(total - 1.0) > 1e-9:
                raise ValueError("known action propensities must sum to one")
        forbidden = {self.assignment_field, self.monetary_outcome}
        if forbidden.intersection(self.pretreatment_features):
            raise ValueError("assignment and outcome cannot be pretreatment features")
        if self.claim_authority is MonetaryAuthority.CONTRIBUTION_PROFIT:
            required = {
                "revenue",
                "cogs",
                "discounts",
                "refunds",
                "shipping",
                "fees",
                "action_cost",
            }
            if not required.issubset(self.profit_components_documented):
                raise ValueError("contribution-profit authority requires every economic component")

    @property
    def bau_action(self) -> str:
        return next(action.name for action in self.actions if action.is_bau)


@dataclass(frozen=True)
class FrozenMonetaryDecision:
    study_id: str
    action: str
    bau: str
    policy_level: PolicyLevel
    disposition: DecisionDisposition
    selected_on_development_only: bool
    freeze_commit: str

    def __post_init__(self) -> None:
        if not self.selected_on_development_only:
            raise ValueError("a frozen decision must be selected on development only")
        if not self.freeze_commit.strip():
            raise ValueError("freeze commit is required")


@dataclass(frozen=True)
class MonetaryProofRow:
    dataset: str
    frozen_decision: str
    bau_value: float
    exergi_value: float
    incremental_value_per_customer: float
    total_incremental_value: float
    lower_95: float
    upper_95: float
    currency: str
    authority: str
    passed: bool

    def __post_init__(self) -> None:
        if self.lower_95 > self.upper_95:
            raise ValueError("confidence interval is reversed")
        if self.passed and self.lower_95 <= 0.0:
            raise ValueError("PASS requires a strictly positive lower confidence bound")


POLICY_HIERARCHY: tuple[PolicyLevel, ...] = (
    PolicyLevel.BAU,
    PolicyLevel.BEST_STATIC,
    PolicyLevel.SEGMENT,
    PolicyLevel.PERSONALIZED,
)

ESTIMATOR_FAMILY: tuple[str, ...] = (
    "raw randomized difference",
    "Lin ANCOVA",
    "cross-fitted AIPW/DR",
    "Hajek/IPW where identified",
    "bootstrap",
    "randomization inference",
)
