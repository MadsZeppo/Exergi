"""Version-pinned, read-only Shopify GraphQL and Bulk Operations client."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen

SHOP_QUERY = """
query ExergiShopMetadata {
  shop { id name currencyCode timezoneOffset timezoneAbbreviation ianaTimezone }
}
"""

ORDERS_BULK_QUERY = """
{
  orders {
    edges { node {
      id createdAt updatedAt cancelledAt displayFinancialStatus displayFulfillmentStatus
      currencyCode customer { id }
      currentSubtotalPriceSet { shopMoney { amount currencyCode } }
      currentTotalDiscountsSet { shopMoney { amount currencyCode } }
      currentShippingPriceSet { shopMoney { amount currencyCode } }
      currentTotalTaxSet { shopMoney { amount currencyCode } }
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      lineItems { edges { node {
        id quantity originalUnitPriceSet { shopMoney { amount currencyCode } }
        discountedUnitPriceAfterAllDiscountsSet { shopMoney { amount currencyCode } }
        product { id } variant { id inventoryItem { id unitCost { amount currencyCode } } }
      } } }
      refunds { id createdAt totalRefundedSet { shopMoney { amount currencyCode } }
        refundLineItems { edges { node { quantity lineItem { id } } } }
      }
      transactions {
        id createdAt kind status gateway amountSet { shopMoney { amount currencyCode } }
      }
      fulfillments { id createdAt updatedAt status }
      returns { edges { node { id status createdAt closedAt
        returnLineItems { edges { node { quantity
          ... on ReturnLineItem { fulfillmentLineItem { id } }
        } } }
      } } }
    } }
  }
}
"""

PRODUCTS_BULK_QUERY = """
{
  products {
    edges { node {
      id title vendor productType status createdAt updatedAt
      variants { edges { node {
        id title sku createdAt updatedAt inventoryItem { id unitCost { amount currencyCode } }
      } } }
    } }
  }
}
"""

CUSTOMERS_BULK_QUERY = """
{
  customers {
    edges { node { id createdAt updatedAt numberOfOrders amountSpent { amount currencyCode } } }
  }
}
"""

BULK_START_MUTATION = """
mutation ExergiBulkStart($query: String!) {
  bulkOperationRunQuery(query: $query) {
    bulkOperation { id status createdAt }
    userErrors { field message }
  }
}
"""

BULK_STATUS_QUERY = """
query ExergiBulkStatus($id: ID!) {
  node(id: $id) { ... on BulkOperation {
    id status errorCode objectCount fileSize url partialDataUrl createdAt completedAt
  } }
}
"""


class GraphQLTransport(Protocol):
    def post(self, endpoint: str, headers: Mapping[str, str], body: bytes) -> bytes: ...

    def get_stream(self, url: str) -> Iterable[bytes]: ...


class UrllibGraphQLTransport:
    def post(self, endpoint: str, headers: Mapping[str, str], body: bytes) -> bytes:
        request = Request(endpoint, data=body, headers=dict(headers), method="POST")
        with urlopen(request, timeout=45) as response:  # noqa: S310 - validated Shopify domain
            return response.read()

    def get_stream(self, url: str) -> Iterable[bytes]:
        request = Request(url, method="GET")
        with urlopen(request, timeout=120) as response:  # noqa: S310 - signed Shopify URL
            while line := response.readline():
                yield line


@dataclass(frozen=True)
class BulkOperation:
    id: str
    status: str
    object_count: int
    url: str | None
    partial_data_url: str | None
    error_code: str | None


TERMINAL_BULK_STATUSES = frozenset({"FAILED", "CANCELED", "EXPIRED"})


class BulkOperationNotFoundError(RuntimeError):
    """A saved Shopify operation no longer exists and cannot be resumed."""


class BulkOperationTerminalError(RuntimeError):
    """A terminal Shopify status containing no query payload or credentials."""

    def __init__(self, status: str, error_code: str | None) -> None:
        self.status = status
        self.error_code = error_code or "UNKNOWN"
        super().__init__(f"Shopify bulk operation {self.status}: {self.error_code}")


class BulkQueryRejectedError(RuntimeError):
    """A data-safe classification of Shopify bulk-query userErrors."""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(f"Shopify rejected bulk query: {error_code}")


class ShopifyGraphQLClient:
    def __init__(
        self,
        shop: str,
        access_token: str,
        api_version: str,
        *,
        transport: GraphQLTransport | None = None,
        max_attempts: int = 5,
    ) -> None:
        self.endpoint = f"https://{shop}/admin/api/{api_version}/graphql.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }
        self.transport = transport or UrllibGraphQLTransport()
        self.max_attempts = max_attempts

    def execute(self, query: str, variables: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = json.loads(self.transport.post(self.endpoint, self.headers, body))
                if not isinstance(response, dict):
                    raise RuntimeError("Shopify GraphQL returned a non-object response")
                if response.get("errors"):
                    raise RuntimeError(f"Shopify GraphQL errors: {response['errors']}")
                return response
            except (OSError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 == self.max_attempts:
                    break
                time.sleep(min(8.0, (2**attempt) + random.random() * 0.25))
        raise RuntimeError("Shopify GraphQL request failed after retries") from last_error

    def shop_metadata(self) -> dict[str, Any]:
        return dict(self.execute(SHOP_QUERY)["data"]["shop"])

    def start_bulk_query(self, query: str) -> BulkOperation:
        payload = self.execute(BULK_START_MUTATION, {"query": query})
        result = payload["data"]["bulkOperationRunQuery"]
        if result["userErrors"]:
            raise BulkQueryRejectedError(_classify_bulk_user_errors(result["userErrors"]))
        return _bulk(result["bulkOperation"])

    def bulk_status(self, operation_id: str) -> BulkOperation:
        payload = self.execute(BULK_STATUS_QUERY, {"id": operation_id})
        node = payload["data"]["node"]
        if not node:
            raise BulkOperationNotFoundError("Shopify bulk operation was not found")
        return _bulk(node)

    def wait_for_bulk(
        self, operation_id: str, *, poll_seconds: float = 2.0, max_polls: int = 900
    ) -> BulkOperation:
        for _ in range(max_polls):
            operation = self.bulk_status(operation_id)
            if operation.status == "COMPLETED":
                return operation
            if operation.status in TERMINAL_BULK_STATUSES:
                raise BulkOperationTerminalError(operation.status, operation.error_code)
            time.sleep(poll_seconds)
        raise TimeoutError("Shopify bulk operation did not complete before polling deadline")

    def iter_jsonl(self, url: str) -> Iterator[dict[str, Any]]:
        for raw_line in self.transport.get_stream(url):
            line = raw_line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError("Shopify bulk JSONL contains a non-object line")
            yield value


def _bulk(value: Mapping[str, Any]) -> BulkOperation:
    return BulkOperation(
        id=str(value["id"]),
        status=str(value["status"]),
        object_count=int(value.get("objectCount") or 0),
        url=value.get("url"),
        partial_data_url=value.get("partialDataUrl"),
        error_code=value.get("errorCode"),
    )


def _classify_bulk_user_errors(values: Any) -> str:
    messages = " ".join(
        str(value.get("message", ""))
        for value in values
        if isinstance(value, Mapping)
    ).lower()
    if "invalid bulk query" in messages or "doesn't exist on type" in messages:
        return "INVALID_QUERY"
    if "access_denied" in messages or "access denied" in messages:
        return "ACCESS_DENIED"
    return "SHOPIFY_USER_ERROR"
