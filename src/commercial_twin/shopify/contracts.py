"""Typed contracts shared by Shopify ingestion, analysis and the dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ValueAuthority(StrEnum):
    OBSERVED = "OBSERVED"
    MERCHANT_ASSUMPTION = "MERCHANT_ASSUMPTION"
    DERIVED = "DERIVED"
    MISSING = "MISSING"


class EconomicAuthority(StrEnum):
    OBSERVED_CONTRIBUTION_PROFIT = "OBSERVED_CONTRIBUTION_PROFIT"
    ESTIMATED_CONTRIBUTION_PROFIT = "ESTIMATED_CONTRIBUTION_PROFIT"
    NET_REVENUE_ONLY = "NET_REVENUE_ONLY"
    GROSS_REVENUE_ONLY = "GROSS_REVENUE_ONLY"
    DATA_NOT_READY = "DATA_NOT_READY"


class Recommendation(StrEnum):
    TEST = "TEST"
    AVOID = "AVOID"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"
    BAU = "BAU"


class Lifecycle(StrEnum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    COOLING = "COOLING"
    DORMANT = "DORMANT"
    REACTIVATED = "REACTIVATED"


@dataclass(frozen=True)
class MoneyComponent:
    amount: float | None
    currency: str
    authority: ValueAuthority
    source: str


@dataclass(frozen=True)
class CanonicalOrderLine:
    source_id: str
    order_source_id: str
    product_source_id: str | None
    variant_source_id: str | None
    quantity: int
    gross_sales: float
    discounts: float
    net_revenue: float
    cogs: MoneyComponent


@dataclass(frozen=True)
class CanonicalRefund:
    source_id: str
    order_source_id: str
    occurred_at: datetime
    amount: float
    currency: str


@dataclass(frozen=True)
class CanonicalOrder:
    shop_id: UUID
    source_id: str
    customer_key: str | None
    occurred_at: datetime
    observed_at: datetime
    currency: str
    gross_sales: float
    discounts: float
    shipping_revenue: float
    tax: float
    refunds: float
    net_revenue: float
    cancelled: bool
    lines: tuple[CanonicalOrderLine, ...] = ()


@dataclass(frozen=True)
class EconomicAssumptions:
    version: str
    valid_from: datetime
    payment_fee_rate: float | None = None
    payment_fixed_fee: float | None = None
    shipping_cost_per_order: float | None = None
    fulfillment_cost_per_order: float | None = None
    action_cost_per_order: float | None = None


@dataclass(frozen=True)
class OrderEconomics:
    order_source_id: str
    net_revenue: MoneyComponent
    cogs: MoneyComponent
    refunds: MoneyComponent
    payment_fees: MoneyComponent
    shipping_subsidy: MoneyComponent
    fulfillment_cost: MoneyComponent
    action_cost: MoneyComponent
    contribution_profit: MoneyComponent
    authority: EconomicAuthority
    completeness: dict[str, bool]


@dataclass(frozen=True)
class CustomerState:
    customer_key: str
    as_of: datetime
    recency_days: int
    purchase_frequency: int
    average_order_value: float
    net_revenue: float
    contribution_profit: float | None
    normal_interpurchase_days: float | None
    lifecycle: Lifecycle
    discount_share: float
    return_rate: float
    tenure_days: int
    category_affinity: tuple[str, ...]
    support: str
    uncertainty: dict[str, Any]


@dataclass(frozen=True)
class CompanyState:
    shop_id: UUID
    as_of: datetime
    currency: str
    order_count: int
    customer_count: int
    net_revenue: float
    contribution_profit: float | None
    repeat_revenue: float
    refund_rate: float
    discount_rate: float
    lifecycle_distribution: dict[str, int]
    economic_authority: EconomicAuthority
    completeness: dict[str, float]


@dataclass(frozen=True)
class Diagnostic:
    kind: str
    title: str
    observation: str
    metrics: dict[str, float | int | str | None]
    authority: str = "OBSERVATIONAL_DESCRIPTIVE"
    causal_effect_identified: bool = False


@dataclass(frozen=True)
class DecisionCard:
    id: str
    created_at: datetime
    observation: str
    economic_significance: str
    affected_population: str
    business_as_usual: str
    possible_action: str
    scenario_range: tuple[float | None, float | None]
    downside: str
    data_basis: tuple[str, ...]
    uncertainty: str
    evidence_authority: str
    reason_codes: tuple[str, ...]
    recommendation: Recommendation
    assumptions: tuple[str, ...] = ()
    what_changes_view: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationReport:
    shop_id: UUID
    as_of: datetime
    currency: str
    admin_totals: dict[str, float | int]
    imported_totals: dict[str, float | int]
    differences: dict[str, float]
    explanations: tuple[str, ...]
    passed: bool


@dataclass(frozen=True)
class DashboardSnapshot:
    connection: dict[str, Any]
    sync: dict[str, Any]
    company_state: CompanyState | None
    diagnostics: tuple[Diagnostic, ...] = ()
    decision_cards: tuple[DecisionCard, ...] = ()
    data_quality: dict[str, Any] = field(default_factory=dict)
