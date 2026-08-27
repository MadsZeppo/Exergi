"""Typed V6 decision families and bounded action banks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DecisionFamily(StrEnum):
    PRICE = "PRICE"
    SHIPPING = "SHIPPING"
    OFFER = "OFFER"
    RETENTION = "RETENTION"


class DecisionDisposition(StrEnum):
    IGNORE = "IGNORE"
    BAU = "BAU"
    TEST = "TEST"
    ACT = "ACT"
    AVOID = "AVOID"


class PolicyGranularity(StrEnum):
    G0_GLOBAL = "G0_GLOBAL"
    G1_SEGMENT = "G1_SEGMENT"
    G2_INDIVIDUAL = "G2_INDIVIDUAL"


@dataclass(frozen=True)
class ActionDefinition:
    action_id: str
    family: DecisionFamily
    label: str
    parameters: tuple[tuple[str, float | str], ...]
    is_bau: bool = False
    reversible: bool = True


@dataclass(frozen=True)
class DecisionContext:
    merchant_id: str
    family: DecisionFamily
    eligible_exposures: int
    action_frequency: float
    contribution_profit_scale: float
    remaining_horizon: int
    evidence_age_days: int


def default_action_banks() -> dict[DecisionFamily, tuple[ActionDefinition, ...]]:
    return {
        DecisionFamily.PRICE: (
            ActionDefinition("price_bau", DecisionFamily.PRICE, "Current price / BAU", (), True),
            ActionDefinition(
                "price_down_5", DecisionFamily.PRICE, "Modest price decrease", (("change", -0.05),)
            ),
            ActionDefinition(
                "price_up_5", DecisionFamily.PRICE, "Modest price increase", (("change", 0.05),)
            ),
        ),
        DecisionFamily.SHIPPING: (
            ActionDefinition(
                "shipping_bau", DecisionFamily.SHIPPING, "Current threshold / BAU", (), True
            ),
            ActionDefinition(
                "shipping_lower", DecisionFamily.SHIPPING, "Lower threshold", (("change", -0.10),)
            ),
            ActionDefinition(
                "shipping_higher", DecisionFamily.SHIPPING, "Higher threshold", (("change", 0.10),)
            ),
        ),
        DecisionFamily.OFFER: (
            ActionDefinition("offer_bau", DecisionFamily.OFFER, "BAU campaign", (), True),
            ActionDefinition("offer_shipping", DecisionFamily.OFFER, "Free shipping", ()),
            ActionDefinition(
                "offer_discount_5", DecisionFamily.OFFER, "5% discount", (("discount", 0.05),)
            ),
            ActionDefinition(
                "offer_discount_10", DecisionFamily.OFFER, "10% discount", (("discount", 0.10),)
            ),
            ActionDefinition(
                "offer_bundle", DecisionFamily.OFFER, "Bundle / multi-buy", (("units", 2.0),)
            ),
        ),
        DecisionFamily.RETENTION: (
            ActionDefinition(
                "retention_bau", DecisionFamily.RETENTION, "BAU lifecycle rule", (), True
            ),
            ActionDefinition("retention_offer", DecisionFamily.RETENTION, "Retention offer", ()),
            ActionDefinition(
                "retention_shipping", DecisionFamily.RETENTION, "Shipping incentive", ()
            ),
            ActionDefinition(
                "retention_discount_5",
                DecisionFamily.RETENTION,
                "Bounded 5% discount",
                (("discount", 0.05),),
            ),
        ),
    }
