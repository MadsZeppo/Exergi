from __future__ import annotations

from typing import Literal

from pydantic import Field

from commercial_twin.schemas import CommercialAction


class DiscountAction(CommercialAction):
    action_type: Literal["discount"] = "discount"
    discount_depth: float = Field(ge=0, le=0.30)
    product_ids: tuple[str, ...] = ()
    category_ids: tuple[str, ...] = ()


class PriceChangeAction(CommercialAction):
    action_type: Literal["price_change"] = "price_change"
    relative_change: float


class FreeShippingAction(CommercialAction):
    action_type: Literal["free_shipping"] = "free_shipping"
    minimum_basket: float = Field(ge=0)


class PromotionAction(CommercialAction):
    action_type: Literal["promotion"] = "promotion"
    promotion_kind: str
