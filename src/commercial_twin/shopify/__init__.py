"""Read-only Shopify vertical slice for the Exergi merchant product."""

from .config import ShopifySettings
from .contracts import EconomicAuthority, Recommendation

__all__ = ["EconomicAuthority", "Recommendation", "ShopifySettings"]
