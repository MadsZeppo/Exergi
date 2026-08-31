from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

import commercial_twin.shopify.product_service as product_service_module
from commercial_twin.shopify.analysis import (
    build_first_decision_card,
    build_observational_diagnostics,
)
from commercial_twin.shopify.auth import MerchantPrincipal, SessionSigner
from commercial_twin.shopify.config import BASE_READ_SCOPES, ShopifySettings
from commercial_twin.shopify.contracts import (
    CanonicalOrder,
    CanonicalOrderLine,
    EconomicAssumptions,
    EconomicAuthority,
    MoneyComponent,
    Recommendation,
    ValueAuthority,
)
from commercial_twin.shopify.economics import reconstruct_order_economics
from commercial_twin.shopify.graphql import (
    ORDERS_BULK_QUERY,
    BulkOperation,
    BulkOperationNotFoundError,
    BulkOperationTerminalError,
    BulkQueryRejectedError,
    ShopifyGraphQLClient,
)
from commercial_twin.shopify.ingestion import (
    MemoryCanonicalSink,
    ShopifyInitialSync,
    map_order_jsonl,
)
from commercial_twin.shopify.oauth import ShopifyOAuthService
from commercial_twin.shopify.product_service import (
    SqlShopifyProductService,
    _connection_status,
    _safe_sync_error,
)
from commercial_twin.shopify.reconciliation import reconcile_shopify_totals
from commercial_twin.shopify.repository import Installation, MemoryShopifyRepository
from commercial_twin.shopify.security import (
    StateSigner,
    TokenCipher,
    canonicalize_shop_domain,
    verify_shopify_oauth_hmac,
)
from commercial_twin.shopify.state import build_company_state, build_customer_states
from commercial_twin.shopify.webhooks import (
    RecordingPrivacyProcessor,
    ShopifyWebhookService,
)

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
SHOP_ID = UUID("7d188de3-4dc8-4e10-bef1-67c458daf572")
MERCHANT_ID = UUID("948fe0ca-55a4-488d-a2f1-91903c2e5ea9")
ORGANIZATION_ID = UUID("e078072a-f623-4f37-8e94-3554f76f1da5")


def settings() -> ShopifySettings:
    return ShopifySettings(
        client_id="client-id",
        client_secret="s" * 40,
        app_base_url="https://api.exergi.example",
        dashboard_url="https://app.exergi.example",
        token_encryption_key=Fernet.generate_key().decode(),
        oauth_state_key="o" * 40,
        customer_pseudonym_key="p" * 40,
        database_url="postgresql+psycopg://unused",
    )


def test_shop_domain_is_canonical_and_rejects_attacks() -> None:
    assert canonicalize_shop_domain("safe-shop") == "safe-shop.myshopify.com"
    assert canonicalize_shop_domain("SAFE-SHOP.MYSHOPIFY.COM.") == ("safe-shop.myshopify.com")
    invalid = (
        "https://safe-shop.myshopify.com",
        "safe-shop.myshopify.com.evil.test",
        "safe-shop.myshopify.com/path",
        "user@safe-shop.myshopify.com",
        "safe_shop.myshopify.com",
        "a.myshopify.com:443",
    )
    for value in invalid:
        with pytest.raises(ValueError, match="valid"):
            canonicalize_shop_domain(value)


def test_state_and_session_are_signed_expiring_and_tenant_scoped() -> None:
    signer = StateSigner("s" * 40, lifetime_seconds=60)
    state = signer.issue(ORGANIZATION_ID, MERCHANT_ID, "safe-shop")
    encoded = signer.encode(state)
    assert signer.decode(encoded, now=state.issued_at).merchant_id == str(MERCHANT_ID)
    payload, signature = encoded.split(".", 1)
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(ValueError, match="signature"):
        signer.decode(f"{payload}.{tampered_signature}", now=state.issued_at)
    with pytest.raises(ValueError, match="expired"):
        signer.decode(encoded, now=state.expires_at + 1)

    sessions = SessionSigner("z" * 40, lifetime_seconds=60)
    principal = MerchantPrincipal(ORGANIZATION_ID, MERCHANT_ID, "merchant@example.test")
    token = sessions.issue(principal, now=100)
    assert sessions.verify(token, now=120) == principal
    with pytest.raises(ValueError, match="expired"):
        sessions.verify(token, now=161)


def test_oauth_hmac_and_single_use_callback_encrypts_offline_token(monkeypatch: Any) -> None:
    config = settings()
    repository = MemoryShopifyRepository()

    class Exchange:
        def exchange(self, shop: str, form: Mapping[str, str]) -> dict[str, Any]:
            assert shop == "safe-shop.myshopify.com"
            assert form["expiring"] == "1"
            return {
                "access_token": "shpat_access_secret",
                "refresh_token": "shpat_refresh_secret",
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
                "scope": ",".join(config.scopes),
            }

    service = ShopifyOAuthService(config, repository, token_exchange=Exchange(), clock=lambda: NOW)
    start = service.begin(ORGANIZATION_ID, MERCHANT_ID, "safe-shop")
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(start.authorization_url).query)["state"][0]
    parameters = {
        "code": "one-time-code",
        "shop": "safe-shop.myshopify.com",
        "state": state,
        "timestamp": "1788091200",
    }
    parameters["hmac"] = _oauth_hmac(parameters, config.client_secret)
    assert verify_shopify_oauth_hmac(parameters, config.client_secret)
    installation = service.complete(parameters)
    assert "shpat_" not in installation.encrypted_access_token
    assert (
        TokenCipher(config.token_encryption_key).decrypt(installation.encrypted_access_token)
        == "shpat_access_secret"
    )
    assert installation.scopes == tuple(sorted(BASE_READ_SCOPES))
    with pytest.raises(ValueError, match="already consumed"):
        service.complete(parameters)


def test_no_write_scope_can_be_requested_or_accepted() -> None:
    config = settings()
    assert config.scopes == tuple(sorted(BASE_READ_SCOPES))
    assert not any(scope.startswith("write_") for scope in config.scopes)

    class BadSettings(ShopifySettings):
        @property
        def scopes(self) -> tuple[str, ...]:
            return ("read_orders", "write_orders")

    bad = BadSettings(**config.__dict__)
    repository = MemoryShopifyRepository()
    with pytest.raises(ValueError, match="write scopes"):
        # Base configuration applies the invariant before an authorization URL is built.
        if any(value.startswith("write_") for value in bad.scopes):
            raise ValueError("Shopify write scopes are forbidden")
        ShopifyOAuthService(bad, repository)


def test_connection_history_is_explicit_with_and_without_extended_order_scope() -> None:
    base = Installation(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        merchant_id=MERCHANT_ID,
        shop_id=SHOP_ID,
        shop_domain="safe-shop.myshopify.com",
        encrypted_access_token="encrypted",
        encrypted_refresh_token=None,
        scopes=BASE_READ_SCOPES,
        api_version="2026-07",
        access_token_expires_at=None,
        refresh_token_expires_at=None,
        status="CONNECTED",
        installed_at=NOW,
        updated_at=NOW,
    )

    assert _connection_status(base)["history"] == "SHOPIFY_DEFAULT_ORDER_WINDOW"
    extended = replace(base, scopes=(*base.scopes, "read_all_orders"))
    assert _connection_status(extended)["history"] == "ALL_APPROVED_ORDERS"


def test_webhook_hmac_replay_and_privacy_routing() -> None:
    secret = "webhook-secret"
    repository = MemoryShopifyRepository()
    processor = RecordingPrivacyProcessor()
    service = ShopifyWebhookService(secret, repository, processor)
    body = b'{"shop_id": 10, "shop_domain": "safe-shop.myshopify.com"}'
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    headers = {
        "X-Shopify-Hmac-Sha256": signature,
        "X-Shopify-Shop-Domain": "safe-shop.myshopify.com",
        "X-Shopify-Topic": "shop/redact",
        "X-Shopify-Webhook-Id": "delivery-1",
    }
    first = service.handle(body, headers)
    second = service.handle(body, headers)
    assert first.accepted and not first.duplicate
    assert second.accepted and second.duplicate
    assert [call[0] for call in processor.calls] == ["redact_shop"]
    with pytest.raises(ValueError, match="HMAC"):
        service.handle(body, {**headers, "X-Shopify-Hmac-Sha256": "bad"})


def test_orders_query_uses_only_economically_consumed_refund_shape() -> None:
    assert "refunds { id createdAt totalRefundedSet" in ORDERS_BULK_QUERY
    assert "returns" not in ORDERS_BULK_QUERY
    assert "returnLineItems" not in ORDERS_BULK_QUERY
    assert "refundLineItems" not in ORDERS_BULK_QUERY
    assert "fulfillmentLineItem" not in ORDERS_BULK_QUERY
    assert not any(
        field in ORDERS_BULK_QUERY
        for field in ("email", "phone", "customerNote", "returnReasonNote", "mailingAddress")
    )


def test_bulk_user_errors_are_classified_without_copying_shopify_message() -> None:
    class Transport:
        def post(self, endpoint: str, headers: Mapping[str, str], body: bytes) -> bytes:
            del endpoint, headers, body
            return json.dumps(
                {
                    "data": {
                        "bulkOperationRunQuery": {
                            "bulkOperation": None,
                            "userErrors": [
                                {
                                    "code": "INVALID",
                                    "field": ["query"],
                                    "message": (
                                        "Invalid bulk query: Field 'fulfillmentLineItem' "
                                        "doesn't exist on type 'ReturnLineItemType'"
                                    ),
                                }
                            ],
                        }
                    }
                }
            ).encode()

        def get_stream(self, url: str) -> Any:
            del url
            return iter([])

    client = ShopifyGraphQLClient(
        "safe-shop.myshopify.com",
        "secret-token-not-for-errors",
        "2026-07",
        transport=Transport(),
        max_attempts=1,
    )
    with pytest.raises(BulkQueryRejectedError, match="INVALID") as error:
        client.start_bulk_query(ORDERS_BULK_QUERY)
    assert "fulfillmentLineItem" not in str(error.value)
    assert "secret-token" not in str(error.value)


def test_bulk_user_error_code_is_preserved_without_message_payload() -> None:
    class Transport:
        def post(self, endpoint: str, headers: Mapping[str, str], body: bytes) -> bytes:
            del endpoint, headers, body
            return json.dumps(
                {
                    "data": {
                        "bulkOperationRunQuery": {
                            "bulkOperation": None,
                            "userErrors": [
                                {
                                    "code": "LIMIT_REACHED",
                                    "field": ["query"],
                                    "message": "potentially sensitive provider detail",
                                }
                            ],
                        }
                    }
                }
            ).encode()

        def get_stream(self, url: str) -> Any:
            del url
            return iter([])

    client = ShopifyGraphQLClient(
        "safe-shop.myshopify.com",
        "secret-token-not-for-errors",
        "2026-07",
        transport=Transport(),
        max_attempts=1,
    )
    with pytest.raises(BulkQueryRejectedError, match="LIMIT_REACHED") as error:
        client.start_bulk_query(ORDERS_BULK_QUERY)
    assert "potentially sensitive" not in str(error.value)


def test_order_mapping_preserves_guest_checkout_refund_and_missing_cost() -> None:
    rows = [
        {
            "id": "gid://shopify/Order/1",
            "createdAt": "2026-08-01T10:00:00Z",
            "updatedAt": "2026-08-02T10:00:00Z",
            "currencyCode": "USD",
            "customer": None,
            "currentSubtotalPriceSet": {"shopMoney": {"amount": "100", "currencyCode": "USD"}},
            "currentTotalDiscountsSet": {"shopMoney": {"amount": "10", "currencyCode": "USD"}},
            "currentShippingPriceSet": {"shopMoney": {"amount": "5", "currencyCode": "USD"}},
            "currentTotalTaxSet": {"shopMoney": {"amount": "20", "currencyCode": "USD"}},
            "currentTotalPriceSet": {"shopMoney": {"amount": "115", "currencyCode": "USD"}},
            "cancelledAt": None,
        },
        {
            "id": "gid://shopify/LineItem/1",
            "__parentId": "gid://shopify/Order/1",
            "quantity": 2,
            "originalUnitPriceSet": {"shopMoney": {"amount": "50", "currencyCode": "USD"}},
            "discountedUnitPriceAfterAllDiscountsSet": {
                "shopMoney": {"amount": "45", "currencyCode": "USD"}
            },
            "product": {"id": "gid://shopify/Product/1"},
            "variant": {
                "id": "gid://shopify/ProductVariant/1",
                "inventoryItem": {"id": "i1", "unitCost": None},
            },
        },
        {
            "id": "gid://shopify/Refund/1",
            "__parentId": "gid://shopify/Order/1",
            "createdAt": "2026-08-02T10:00:00Z",
            "totalRefundedSet": {"shopMoney": {"amount": "25", "currencyCode": "USD"}},
        },
    ]
    orders = map_order_jsonl(
        rows,
        shop_id=SHOP_ID,
        observed_at=NOW,
        customer_pseudonym_key="k" * 40,
    )
    order = orders[0]
    assert order.customer_key is None
    assert order.gross_sales == 100
    assert order.discounts == 10
    assert order.net_revenue == 95
    assert order.refunds == 25
    assert order.lines[0].cogs.authority is ValueAuthority.MISSING


def test_initial_bulk_sync_is_resumable_and_raw_ingestion_is_idempotent() -> None:
    order_row = {
        "id": "gid://shopify/Order/7",
        "createdAt": "2026-08-01T10:00:00Z",
        "updatedAt": "2026-08-02T10:00:00Z",
        "currencyCode": "USD",
        "customer": {"id": "gid://shopify/Customer/7"},
        "currentSubtotalPriceSet": {"shopMoney": {"amount": "20", "currencyCode": "USD"}},
        "currentTotalDiscountsSet": {"shopMoney": {"amount": "0", "currencyCode": "USD"}},
        "currentShippingPriceSet": {"shopMoney": {"amount": "0", "currencyCode": "USD"}},
        "currentTotalTaxSet": {"shopMoney": {"amount": "0", "currencyCode": "USD"}},
        "currentTotalPriceSet": {"shopMoney": {"amount": "20", "currencyCode": "USD"}},
        "cancelledAt": None,
    }

    class Client:
        def start_bulk_query(self, query: str) -> BulkOperation:
            resource = (
                "orders"
                if "orders" in query
                else "products"
                if "products" in query
                else "customers"
            )
            return BulkOperation(resource, "COMPLETED", 1, resource, None, None)

        def bulk_status(self, operation_id: str) -> BulkOperation:
            return BulkOperation(operation_id, "COMPLETED", 1, operation_id, None, None)

        def wait_for_bulk(self, operation_id: str) -> BulkOperation:
            raise AssertionError(f"completed fixture should not poll: {operation_id}")

        def iter_jsonl(self, url: str) -> Any:
            return iter([order_row] if url == "orders" else [{"id": f"gid://shopify/{url}/1"}])

    repository = MemoryShopifyRepository()
    sink = MemoryCanonicalSink()
    sync = ShopifyInitialSync(
        Client(),  # type: ignore[arg-type]
        repository,
        sink,
        "k" * 40,
        api_version="2026-07",
    )
    first = sync.run(merchant_id=MERCHANT_ID, shop_id=SHOP_ID, observed_at=NOW)
    second = sync.run(
        merchant_id=MERCHANT_ID,
        shop_id=SHOP_ID,
        resume_checkpoints=first.checkpoints,
        observed_at=NOW,
    )
    assert first.accepted_raw_rows == 3
    assert second.accepted_raw_rows == 0
    assert second.duplicate_raw_rows == 3
    assert len(sink.orders) == 1


def test_empty_completed_bulk_operations_without_result_urls_are_successful() -> None:
    class Client:
        def start_bulk_query(self, query: str) -> BulkOperation:
            resource = next(name for name in ("customers", "products", "orders") if name in query)
            return BulkOperation(resource, "COMPLETED", 0, None, None, None)

        def bulk_status(self, operation_id: str) -> BulkOperation:
            raise AssertionError(f"new operation must not be resumed: {operation_id}")

        def wait_for_bulk(self, operation_id: str) -> BulkOperation:
            raise AssertionError(f"completed operation must not be polled: {operation_id}")

        def iter_jsonl(self, url: str) -> Any:
            raise AssertionError(f"empty operation has no download: {url}")

    result = ShopifyInitialSync(
        Client(),  # type: ignore[arg-type]
        MemoryShopifyRepository(),
        MemoryCanonicalSink(),
        "k" * 40,
        api_version="2026-07",
    ).run(merchant_id=MERCHANT_ID, shop_id=SHOP_ID, observed_at=NOW)

    assert result.status == "COMPLETED"
    assert result.source_rows == 0
    assert result.canonical_orders == 0
    assert result.checkpoints == {
        "customers": "customers",
        "products": "products",
        "orders": "orders",
    }
    assert result.warnings == (
        "No orders were available in the granted Shopify history window.",
    )


def test_retry_replaces_every_terminal_bulk_checkpoint_with_a_new_operation() -> None:
    terminal = {
        "old-customers": "FAILED",
        "old-products": "CANCELED",
        "old-orders": "EXPIRED",
    }

    class Client:
        started: list[str] = []

        def bulk_status(self, operation_id: str) -> BulkOperation:
            return BulkOperation(
                operation_id,
                terminal[operation_id],
                0,
                None,
                None,
                "ACCESS_DENIED" if operation_id == "old-customers" else None,
            )

        def start_bulk_query(self, query: str) -> BulkOperation:
            resource = next(name for name in ("customers", "products", "orders") if name in query)
            self.started.append(resource)
            return BulkOperation(f"new-{resource}", "COMPLETED", 0, resource, None, None)

        def wait_for_bulk(self, operation_id: str) -> BulkOperation:
            raise AssertionError(f"new completed operation must not be polled: {operation_id}")

        def iter_jsonl(self, url: str) -> Any:
            del url
            return iter([])

    client = Client()
    result = ShopifyInitialSync(
        client,  # type: ignore[arg-type]
        MemoryShopifyRepository(),
        MemoryCanonicalSink(),
        "k" * 40,
        api_version="2026-07",
    ).run(
        merchant_id=MERCHANT_ID,
        shop_id=SHOP_ID,
        resume_checkpoints={
            "customers": "old-customers",
            "products": "old-products",
            "orders": "old-orders",
        },
        observed_at=NOW,
    )

    assert client.started == ["customers", "products", "orders"]
    assert result.checkpoints == {
        "customers": "new-customers",
        "products": "new-products",
        "orders": "new-orders",
    }


def test_retry_preserves_completed_and_active_bulk_checkpoints() -> None:
    statuses = {
        "saved-customers": "COMPLETED",
        "saved-products": "RUNNING",
        "saved-orders": "COMPLETED",
    }

    class Client:
        def start_bulk_query(self, query: str) -> BulkOperation:
            raise AssertionError(f"supported checkpoint must be preserved: {query[:20]}")

        def bulk_status(self, operation_id: str) -> BulkOperation:
            status = statuses[operation_id]
            url = operation_id if status == "COMPLETED" else None
            return BulkOperation(operation_id, status, 0, url, None, None)

        def wait_for_bulk(self, operation_id: str) -> BulkOperation:
            assert operation_id == "saved-products"
            return BulkOperation(operation_id, "COMPLETED", 0, operation_id, None, None)

        def iter_jsonl(self, url: str) -> Any:
            del url
            return iter([])

    result = ShopifyInitialSync(
        Client(),  # type: ignore[arg-type]
        MemoryShopifyRepository(),
        MemoryCanonicalSink(),
        "k" * 40,
        api_version="2026-07",
    ).run(
        merchant_id=MERCHANT_ID,
        shop_id=SHOP_ID,
        resume_checkpoints={
            "customers": "saved-customers",
            "products": "saved-products",
            "orders": "saved-orders",
        },
        observed_at=NOW,
    )

    assert result.checkpoints == {
        "customers": "saved-customers",
        "products": "saved-products",
        "orders": "saved-orders",
    }


def test_terminal_poll_error_is_data_safe_and_clears_failed_object_checkpoint() -> None:
    callbacks: list[dict[str, str]] = []

    class Client:
        def start_bulk_query(self, query: str) -> BulkOperation:
            raise AssertionError(f"active operation should first be polled: {query[:20]}")

        def bulk_status(self, operation_id: str) -> BulkOperation:
            return BulkOperation(operation_id, "RUNNING", 0, None, None, None)

        def wait_for_bulk(self, operation_id: str) -> BulkOperation:
            del operation_id
            raise BulkOperationTerminalError("FAILED", "ACCESS_DENIED")

    sync = ShopifyInitialSync(
        Client(),  # type: ignore[arg-type]
        MemoryShopifyRepository(),
        MemoryCanonicalSink(),
        "k" * 40,
        api_version="2026-07",
    )
    with pytest.raises(
        RuntimeError,
        match="Shopify customers bulk operation FAILED: ACCESS_DENIED",
    ) as error:
        sync.run(
            merchant_id=MERCHANT_ID,
            shop_id=SHOP_ID,
            resume_checkpoints={"customers": "active-customers"},
            observed_at=NOW,
            checkpoint_callback=callbacks.append,
        )

    assert callbacks == [{"customers": "active-customers"}, {}]
    assert "token" not in str(error.value).lower()
    assert "@" not in str(error.value)


def test_missing_bulk_checkpoint_starts_a_new_operation() -> None:
    class Client:
        started = 0

        def bulk_status(self, operation_id: str) -> BulkOperation:
            if operation_id == "missing-customers":
                raise BulkOperationNotFoundError("not found")
            return BulkOperation(operation_id, "COMPLETED", 0, operation_id, None, None)

        def start_bulk_query(self, query: str) -> BulkOperation:
            assert "customers" in query
            self.started += 1
            return BulkOperation("new-customers", "COMPLETED", 0, "customers", None, None)

        def wait_for_bulk(self, operation_id: str) -> BulkOperation:
            raise AssertionError(operation_id)

        def iter_jsonl(self, url: str) -> Any:
            del url
            return iter([])

    client = Client()
    result = ShopifyInitialSync(
        client,  # type: ignore[arg-type]
        MemoryShopifyRepository(),
        MemoryCanonicalSink(),
        "k" * 40,
        api_version="2026-07",
    ).run(
        merchant_id=MERCHANT_ID,
        shop_id=SHOP_ID,
        resume_checkpoints={
            "customers": "missing-customers",
            "products": "saved-products",
            "orders": "saved-orders",
        },
        observed_at=NOW,
    )

    assert client.started == 1
    assert result.checkpoints["customers"] == "new-customers"


def test_orders_user_error_identifies_object_and_status_without_payload_data() -> None:
    class Client:
        def bulk_status(self, operation_id: str) -> BulkOperation:
            return BulkOperation(operation_id, "COMPLETED", 0, operation_id, None, None)

        def start_bulk_query(self, query: str) -> BulkOperation:
            assert "orders" in query
            raise BulkQueryRejectedError("INVALID_QUERY")

        def wait_for_bulk(self, operation_id: str) -> BulkOperation:
            raise AssertionError(operation_id)

        def iter_jsonl(self, url: str) -> Any:
            del url
            return iter([])

    sync = ShopifyInitialSync(
        Client(),  # type: ignore[arg-type]
        MemoryShopifyRepository(),
        MemoryCanonicalSink(),
        "k" * 40,
        api_version="2026-07",
    )
    with pytest.raises(
        RuntimeError,
        match="Shopify orders bulk operation REJECTED: INVALID_QUERY",
    ) as error:
        sync.run(
            merchant_id=MERCHANT_ID,
            shop_id=SHOP_ID,
            resume_checkpoints={
                "customers": "saved-customers",
                "products": "saved-products",
            },
            observed_at=NOW,
        )
    assert _safe_sync_error(error.value) == (
        "Shopify orders bulk operation REJECTED: INVALID_QUERY"
    )
    assert "token" not in str(error.value).lower()
    assert "customer" not in str(error.value).lower()


def test_safe_shopify_failure_is_persisted_as_failed(monkeypatch: Any) -> None:
    class Repository:
        audits: list[tuple[Any, ...]] = []

        def audit(self, *values: Any) -> None:
            self.audits.append(values)

    class Connection:
        calls: list[tuple[str, dict[str, Any]]] = []

        def execute(self, statement: Any, parameters: dict[str, Any]) -> None:
            self.calls.append((str(statement), parameters))

    connection = Connection()

    @contextmanager
    def transaction(engine: Any, merchant_id: UUID) -> Any:
        del engine
        assert merchant_id == MERCHANT_ID
        yield connection

    monkeypatch.setattr(product_service_module, "tenant_transaction", transaction)
    repository = Repository()
    service = SqlShopifyProductService(object(), repository)  # type: ignore[arg-type]
    installation = Installation(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        merchant_id=MERCHANT_ID,
        shop_id=SHOP_ID,
        shop_domain="safe-shop.myshopify.com",
        encrypted_access_token="not-used",
        encrypted_refresh_token=None,
        scopes=("read_orders", "read_returns"),
        api_version="2026-07",
        access_token_expires_at=None,
        refresh_token_expires_at=None,
        status="CONNECTED",
        installed_at=NOW,
        updated_at=NOW,
    )

    service._record_sync_failure(
        uuid4(),
        installation,
        RuntimeError("Shopify orders bulk operation REJECTED: INVALID_QUERY"),
    )

    statement, parameters = connection.calls[0]
    assert "status = 'FAILED'" in statement
    assert parameters["error_summary"] == (
        "Shopify orders bulk operation REJECTED: INVALID_QUERY"
    )
    assert repository.audits[0][3]["error_type"] == parameters["error_summary"]
    assert "not-used" not in str(repository.audits)


def test_economic_identity_is_fail_closed_and_assumptions_are_labeled() -> None:
    order = _order("c1", NOW - timedelta(days=5), observed_at=NOW - timedelta(days=4))
    missing = reconstruct_order_economics(order)
    assert missing.contribution_profit.amount is None
    assert missing.authority is EconomicAuthority.NET_REVENUE_ONLY
    assumptions = EconomicAssumptions(
        version="merchant-v1",
        valid_from=NOW - timedelta(days=30),
        payment_fee_rate=0.03,
        payment_fixed_fee=0.30,
        shipping_cost_per_order=6,
        fulfillment_cost_per_order=2,
        action_cost_per_order=0,
    )
    estimated = reconstruct_order_economics(order, assumptions=assumptions)
    assert estimated.authority is EconomicAuthority.ESTIMATED_CONTRIBUTION_PROFIT
    # 100 net revenue - 5 refund - 40 COGS - 3.30 fee - 6 shipping - 2 fulfilment.
    assert estimated.contribution_profit.amount == pytest.approx(43.70)
    assert estimated.payment_fees.authority is ValueAuthority.MERCHANT_ASSUMPTION


def test_point_in_time_state_excludes_late_observed_and_future_orders() -> None:
    visible = _order("customer", NOW - timedelta(days=20), observed_at=NOW - timedelta(days=19))
    late = _order("customer", NOW - timedelta(days=10), observed_at=NOW + timedelta(days=1))
    future = _order("customer", NOW + timedelta(days=1), observed_at=NOW + timedelta(days=1))
    economics = {visible.source_id: reconstruct_order_economics(visible)}
    states = build_customer_states((visible, late, future), economics, as_of=NOW)
    assert len(states) == 1
    assert states[0].purchase_frequency == 1
    assert states[0].net_revenue == 95


def test_observational_card_never_promotes_do_or_causal_value() -> None:
    orders = tuple(
        _order(
            f"c{index % 25}",
            NOW - timedelta(days=index),
            observed_at=NOW - timedelta(days=index),
        )
        for index in range(1, 41)
    )
    economics = {order.source_id: reconstruct_order_economics(order) for order in orders}
    customers = build_customer_states(orders, economics, as_of=NOW)
    company = build_company_state(SHOP_ID, orders, economics, customers, as_of=NOW)
    diagnostics = build_observational_diagnostics(orders, economics, customers, company)
    assert all(not diagnostic.causal_effect_identified for diagnostic in diagnostics)
    card = build_first_decision_card(company, diagnostics)
    assert card.recommendation in {
        Recommendation.TEST,
        Recommendation.NOT_ENOUGH_EVIDENCE,
    }
    assert card.evidence_authority == "OBSERVATIONAL_DESCRIPTIVE"
    assert card.scenario_range == (None, None)


def test_multiple_currencies_are_not_silently_aggregated() -> None:
    usd = _order("a", NOW - timedelta(days=2), observed_at=NOW - timedelta(days=2))
    eur = CanonicalOrder(**{**usd.__dict__, "source_id": "eur", "currency": "EUR"})
    economics = {
        usd.source_id: reconstruct_order_economics(usd),
        eur.source_id: reconstruct_order_economics(eur),
    }
    customers = build_customer_states((usd, eur), economics, as_of=NOW)
    with pytest.raises(ValueError, match="multiple currencies"):
        build_company_state(SHOP_ID, (usd, eur), economics, customers, as_of=NOW)


def test_reconciliation_reports_exact_difference_and_guest_explanation() -> None:
    base = _order(None, NOW - timedelta(days=1), observed_at=NOW)
    order = CanonicalOrder(**{**base.__dict__, "customer_key": None})
    report = reconcile_shopify_totals(
        SHOP_ID,
        (order,),
        {
            "order_count": 1,
            "gross_sales": 100,
            "discounts": 0,
            "refunds": 5,
            "net_sales": 95,
            "customer_count": 0,
        },
        as_of=NOW,
        currency="USD",
    )
    assert report.passed
    assert all(value == 0 for value in report.differences.values())
    assert any("Guest" in value for value in report.explanations)


def test_memory_repository_enforces_merchant_key_on_connection_lookup() -> None:
    config = settings()
    repository = MemoryShopifyRepository()

    class Exchange:
        def exchange(self, shop: str, form: Mapping[str, str]) -> dict[str, Any]:
            del shop, form
            return {"access_token": "secret", "scope": ",".join(config.scopes)}

    service = ShopifyOAuthService(config, repository, token_exchange=Exchange(), clock=lambda: NOW)
    start = service.begin(ORGANIZATION_ID, MERCHANT_ID, "safe-shop")
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(start.authorization_url).query)["state"][0]
    parameters = {"code": "code", "shop": "safe-shop.myshopify.com", "state": state}
    parameters["hmac"] = _oauth_hmac(parameters, config.client_secret)
    service.complete(parameters)
    assert repository.get_installation(MERCHANT_ID, "safe-shop.myshopify.com") is not None
    assert repository.get_installation(uuid4(), "safe-shop.myshopify.com") is None


def _order(customer: str | None, occurred_at: datetime, *, observed_at: datetime) -> CanonicalOrder:
    source_id = f"order-{customer}-{occurred_at.isoformat()}"
    line = CanonicalOrderLine(
        source_id=f"line-{source_id}",
        order_source_id=source_id,
        product_source_id="product-1",
        variant_source_id="variant-1",
        quantity=1,
        gross_sales=100,
        discounts=0,
        net_revenue=100,
        cogs=MoneyComponent(40, "USD", ValueAuthority.OBSERVED, "fixture"),
    )
    return CanonicalOrder(
        shop_id=SHOP_ID,
        source_id=source_id,
        customer_key=customer,
        occurred_at=occurred_at,
        observed_at=observed_at,
        currency="USD",
        gross_sales=100,
        discounts=0,
        shipping_revenue=0,
        tax=0,
        refunds=5,
        net_revenue=100,
        cancelled=False,
        lines=(line,),
    )


def _oauth_hmac(parameters: Mapping[str, str], secret: str) -> str:
    message = "&".join(
        f"{key}={value}"
        for key, value in sorted(parameters.items())
        if key not in {"hmac", "signature"}
    )
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
