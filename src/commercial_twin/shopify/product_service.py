"""Read model that turns persisted canonical commerce data into the first product analysis."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from commercial_twin.database_security import tenant_transaction

from .analysis import build_first_decision_card, build_observational_diagnostics
from .config import ShopifySettings
from .contracts import (
    CanonicalOrder,
    CanonicalOrderLine,
    DashboardSnapshot,
    EconomicAssumptions,
    MoneyComponent,
    ValueAuthority,
)
from .economics import reconstruct_order_economics
from .graphql import ShopifyGraphQLClient
from .ingestion import ShopifyInitialSync, SqlCanonicalSink, SyncResult
from .repository import Installation, SqlShopifyRepository
from .security import TokenCipher
from .state import build_company_state, build_customer_states


class SqlShopifyProductService:
    def __init__(self, engine: Engine, repository: SqlShopifyRepository) -> None:
        self.engine = engine
        self.repository = repository

    def dashboard(
        self, merchant_id: UUID, shop_domain: str, *, as_of: datetime | None = None
    ) -> DashboardSnapshot:
        installation = self.repository.get_installation(merchant_id, shop_domain)
        if installation is None:
            return DashboardSnapshot(
                connection={"status": "NOT_CONNECTED", "shop": shop_domain},
                sync={"status": "NOT_STARTED"},
                company_state=None,
                data_quality={"status": "DATA_NOT_READY", "reason": "SHOPIFY_NOT_CONNECTED"},
            )
        as_of = as_of or datetime.now(UTC)
        orders = self._orders(merchant_id, installation.shop_id)
        if not orders:
            return DashboardSnapshot(
                connection=_connection_status(installation),
                sync=self._latest_sync(merchant_id, installation.shop_id),
                company_state=None,
                data_quality={"status": "DATA_NOT_READY", "reason": "NO_MATURE_ORDERS"},
            )
        assumptions = self._assumptions(merchant_id, installation.shop_id, as_of)
        economics = {
            order.source_id: reconstruct_order_economics(order, assumptions=assumptions)
            for order in orders
        }
        customers = build_customer_states(orders, economics, as_of=as_of)
        company = build_company_state(
            installation.shop_id, orders, economics, customers, as_of=as_of
        )
        diagnostics = build_observational_diagnostics(orders, economics, customers, company)
        decision = build_first_decision_card(company, diagnostics)
        return DashboardSnapshot(
            connection=_connection_status(installation),
            sync=self._latest_sync(merchant_id, installation.shop_id),
            company_state=company,
            diagnostics=diagnostics,
            decision_cards=(decision,),
            data_quality={
                "status": (
                    "READY_WITH_LIMITATIONS"
                    if company.economic_authority.value != "DATA_NOT_READY"
                    else "DATA_NOT_READY"
                ),
                "economic_authority": company.economic_authority.value,
                "completeness": company.completeness,
                "customer_state_count": len(customers),
                "causal_action_effect_identified": False,
            },
        )

    def save_assumptions(
        self,
        merchant_id: UUID,
        shop_id: UUID,
        *,
        version: str,
        valid_from: datetime,
        assumptions: dict[str, float | None],
        actor: str,
    ) -> None:
        allowed = {
            "payment_fee_rate",
            "payment_fixed_fee",
            "shipping_cost_per_order",
            "fulfillment_cost_per_order",
            "action_cost_per_order",
        }
        if set(assumptions) - allowed:
            raise ValueError("unsupported economic assumption")
        if any(value is not None and value < 0 for value in assumptions.values()):
            raise ValueError("economic assumptions cannot be negative")
        payment_fee_rate = assumptions.get("payment_fee_rate")
        if payment_fee_rate is not None and payment_fee_rate > 1:
            raise ValueError("payment fee rate must be between 0 and 1")
        with tenant_transaction(self.engine, merchant_id) as connection:
            connection.execute(
                text("""
                INSERT INTO economic_assumptions
                    (merchant_id, shop_id, version, valid_from, assumptions_json, created_by)
                VALUES (:merchant_id, :shop_id, :version, :valid_from,
                        CAST(:assumptions AS jsonb), :actor)
                """),
                {
                    "merchant_id": merchant_id,
                    "shop_id": shop_id,
                    "version": version,
                    "valid_from": valid_from,
                    "assumptions": json.dumps(assumptions, sort_keys=True),
                    "actor": actor,
                },
            )

    def initial_sync(
        self,
        settings: ShopifySettings,
        installation: Installation,
    ) -> SyncResult:
        sync_run_id = uuid4()
        started = datetime.now(UTC)
        resume = self._resume_checkpoints(installation.merchant_id, installation.shop_id)
        with tenant_transaction(self.engine, installation.merchant_id) as connection:
            connection.execute(
                text("""
                INSERT INTO sync_runs
                    (id, merchant_id, connection_id, shop_id, sync_type, started_at,
                     status, source_rows, accepted_rows, rejected_rows, duplicate_rows,
                     checkpoint_json)
                VALUES (:id, :merchant_id, :connection_id, :shop_id, 'INITIAL_BULK',
                        :started_at, 'RUNNING', 0, 0, 0, 0, CAST(:checkpoints AS jsonb))
                """),
                {
                    "id": sync_run_id,
                    "merchant_id": installation.merchant_id,
                    "connection_id": installation.id,
                    "shop_id": installation.shop_id,
                    "started_at": started,
                    "checkpoints": json.dumps(resume, sort_keys=True),
                },
            )
        try:
            token = TokenCipher(settings.token_encryption_key).decrypt(
                installation.encrypted_access_token
            )
            client = ShopifyGraphQLClient(installation.shop_domain, token, settings.api_version)
            metadata = client.shop_metadata()
            with tenant_transaction(self.engine, installation.merchant_id) as connection:
                connection.execute(
                    text("""
                INSERT INTO shops
                    (id, merchant_id, source_shop_id, shop_domain, name, currency,
                     iana_timezone, source_version, observed_at)
                VALUES (:id, :merchant_id, :source_id, :shop_domain, :name, :currency,
                        :timezone, :version, :observed_at)
                ON CONFLICT (merchant_id, shop_domain) DO UPDATE SET
                    source_shop_id = EXCLUDED.source_shop_id, name = EXCLUDED.name,
                    currency = EXCLUDED.currency, iana_timezone = EXCLUDED.iana_timezone,
                    source_version = EXCLUDED.source_version, observed_at = EXCLUDED.observed_at,
                    deletion_status = 'ACTIVE'
                    """),
                    {
                        "id": installation.shop_id,
                        "merchant_id": installation.merchant_id,
                        "source_id": metadata.get("id"),
                        "shop_domain": installation.shop_domain,
                        "name": metadata.get("name"),
                        "currency": metadata.get("currencyCode"),
                        "timezone": metadata.get("ianaTimezone"),
                        "version": settings.api_version,
                        "observed_at": started,
                    },
                )
            sink = SqlCanonicalSink(self.engine, installation.merchant_id, settings.api_version)
            sync = ShopifyInitialSync(
                client,
                self.repository,
                sink,
                settings.customer_pseudonym_key,
                api_version=settings.api_version,
            )
        except Exception as exc:
            self._record_sync_failure(sync_run_id, installation, exc)
            raise
        try:
            result = sync.run(
                merchant_id=installation.merchant_id,
                shop_id=installation.shop_id,
                resume_checkpoints=resume,
                observed_at=started,
                sync_run_id=sync_run_id,
                        checkpoint_callback=lambda value: self._save_checkpoint(
                            sync_run_id, installation.merchant_id, value
                        ),
            )
            with tenant_transaction(self.engine, installation.merchant_id) as connection:
                connection.execute(
                    text("""
                    UPDATE sync_runs SET completed_at = now(), status = :status,
                        source_rows = :source_rows, accepted_rows = :accepted_rows,
                        duplicate_rows = :duplicate_rows,
                        checkpoint_json = CAST(:checkpoints AS jsonb)
                    WHERE id = :id AND merchant_id = :merchant_id
                    """),
                    {
                        "id": result.sync_run_id,
                        "merchant_id": installation.merchant_id,
                        "status": result.status,
                        "source_rows": result.source_rows,
                        "accepted_rows": result.accepted_raw_rows,
                        "duplicate_rows": result.duplicate_raw_rows,
                        "checkpoints": json.dumps(result.checkpoints, sort_keys=True),
                    },
                )
            return result
        except Exception as exc:
            self._record_sync_failure(sync_run_id, installation, exc)
            raise

    def _record_sync_failure(
        self, sync_run_id: UUID, installation: Installation, error: Exception
    ) -> None:
        # No token, payload or personal field is included in the stored summary.
        summary = _safe_sync_error(error)
        self.repository.audit(
            installation.merchant_id,
            "SHOPIFY_INITIAL_SYNC_FAILED",
            "sync_worker",
            {
                "shop": installation.shop_domain,
                "error_type": summary,
            },
        )
        with tenant_transaction(self.engine, installation.merchant_id) as connection:
            connection.execute(
                text("""
                UPDATE sync_runs SET completed_at = now(), status = 'FAILED',
                    error_summary = :error_summary
                WHERE id = :id AND merchant_id = :merchant_id
                """),
                {
                    "id": sync_run_id,
                    "merchant_id": installation.merchant_id,
                    "error_summary": summary,
                },
            )

    def _save_checkpoint(
        self, sync_run_id: UUID, merchant_id: UUID, checkpoints: dict[str, str]
    ) -> None:
        with tenant_transaction(self.engine, merchant_id) as connection:
            connection.execute(
                text("""
                UPDATE sync_runs SET checkpoint_json = CAST(:checkpoints AS jsonb)
                WHERE id = :id
                """),
                {"id": sync_run_id, "checkpoints": json.dumps(checkpoints, sort_keys=True)},
            )

    def _resume_checkpoints(self, merchant_id: UUID, shop_id: UUID) -> dict[str, str]:
        with tenant_transaction(self.engine, merchant_id) as connection:
            row = (
                connection.execute(
                    text("""
                SELECT checkpoint_json FROM sync_runs
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id AND status = 'FAILED'
                ORDER BY started_at DESC LIMIT 1
                """),
                    {"merchant_id": merchant_id, "shop_id": shop_id},
                )
                .mappings()
                .first()
            )
        if row is None:
            return {}
        value = row["checkpoint_json"]
        return dict(json.loads(value) if isinstance(value, str) else value)

    def _orders(self, merchant_id: UUID, shop_id: UUID) -> tuple[CanonicalOrder, ...]:
        with tenant_transaction(self.engine, merchant_id) as connection:
            order_rows = (
                connection.execute(
                    text("""
                SELECT o.id, o.external_order_id, o.customer_id, o.ordered_at, o.observed_at,
                       o.currency, o.gross_item_sales, o.line_discounts, o.shipping_revenue,
                       o.tax, o.net_sales, o.financial_status,
                       c.pseudonymous_customer_key,
                       COALESCE((SELECT sum(r.refund_amount) FROM refunds r WHERE r.order_id = o.id
                                 AND r.deletion_status = 'ACTIVE'), 0) refunds
                FROM orders o LEFT JOIN customers c ON c.id = o.customer_id
                WHERE o.merchant_id = :merchant_id AND o.shop_id = :shop_id
                  AND o.deletion_status = 'ACTIVE'
                ORDER BY o.ordered_at, o.external_order_id
                """),
                    {"merchant_id": merchant_id, "shop_id": shop_id},
                )
                .mappings()
                .all()
            )
            line_rows = (
                connection.execute(
                    text("""
                SELECT ol.*, p.external_product_id, v.external_variant_id
                FROM order_lines ol
                LEFT JOIN products p ON p.id = ol.product_id
                LEFT JOIN variants v ON v.id = ol.variant_id
                WHERE ol.merchant_id = :merchant_id AND ol.shop_id = :shop_id
                  AND ol.deletion_status = 'ACTIVE'
                """),
                    {"merchant_id": merchant_id, "shop_id": shop_id},
                )
                .mappings()
                .all()
            )
        by_order: dict[UUID, list[Any]] = {}
        for row in line_rows:
            by_order.setdefault(row["order_id"], []).append(row)
        output: list[CanonicalOrder] = []
        for row in order_rows:
            currency = row["currency"]
            lines = tuple(
                self._line(value, row["external_order_id"], currency)
                for value in by_order.get(row["id"], [])
            )
            output.append(
                CanonicalOrder(
                    shop_id=shop_id,
                    source_id=row["external_order_id"],
                    customer_key=row["pseudonymous_customer_key"],
                    occurred_at=row["ordered_at"],
                    observed_at=row["observed_at"] or row["ordered_at"],
                    currency=currency,
                    gross_sales=float(row["gross_item_sales"]),
                    discounts=float(row["line_discounts"]),
                    shipping_revenue=float(row["shipping_revenue"]),
                    tax=float(row["tax"]),
                    refunds=float(row["refunds"]),
                    net_revenue=float(row["net_sales"]),
                    cancelled=row["financial_status"] == "CANCELLED",
                    lines=lines,
                )
            )
        return tuple(output)

    @staticmethod
    def _line(row: Any, order_source_id: str, currency: str) -> CanonicalOrderLine:
        unit_cost = row["cogs_per_unit_nullable"]
        quantity = int(row["quantity"])
        return CanonicalOrderLine(
            source_id=str(row["id"]),
            order_source_id=order_source_id,
            product_source_id=row["external_product_id"],
            variant_source_id=row["external_variant_id"],
            quantity=quantity,
            gross_sales=float(row["gross_unit_price"]) * quantity,
            discounts=float(row["line_discount"]),
            net_revenue=float(row["net_line_sales"]),
            cogs=MoneyComponent(
                float(unit_cost) * quantity if unit_cost is not None else None,
                currency,
                ValueAuthority.OBSERVED if unit_cost is not None else ValueAuthority.MISSING,
                "Shopify InventoryItem.unitCost",
            ),
        )

    def _assumptions(
        self, merchant_id: UUID, shop_id: UUID, as_of: datetime
    ) -> EconomicAssumptions | None:
        with tenant_transaction(self.engine, merchant_id) as connection:
            row = (
                connection.execute(
                    text("""
                SELECT version, valid_from, assumptions_json FROM economic_assumptions
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                  AND valid_from <= :as_of AND (valid_to IS NULL OR valid_to > :as_of)
                ORDER BY valid_from DESC LIMIT 1
                """),
                    {"merchant_id": merchant_id, "shop_id": shop_id, "as_of": as_of},
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        values = row["assumptions_json"]
        if isinstance(values, str):
            values = json.loads(values)
        allowed = {
            "payment_fee_rate",
            "payment_fixed_fee",
            "shipping_cost_per_order",
            "fulfillment_cost_per_order",
            "action_cost_per_order",
        }
        return EconomicAssumptions(
            version=row["version"],
            valid_from=row["valid_from"],
            **{key: value for key, value in values.items() if key in allowed},
        )

    def _latest_sync(self, merchant_id: UUID, shop_id: UUID) -> dict[str, Any]:
        with tenant_transaction(self.engine, merchant_id) as connection:
            row = (
                connection.execute(
                    text("""
                SELECT status, started_at, completed_at, source_rows, accepted_rows,
                       rejected_rows, duplicate_rows, error_summary
                FROM sync_runs WHERE merchant_id = :merchant_id
                  AND shop_id = :shop_id
                ORDER BY started_at DESC LIMIT 1
                """),
                    {"merchant_id": merchant_id, "shop_id": shop_id},
                )
                .mappings()
                .first()
            )
        return dict(row) if row else {"status": "NOT_STARTED"}


def _connection_status(installation: Installation) -> dict[str, Any]:
    return {
        "status": installation.status,
        "shop": installation.shop_domain,
        "api_version": installation.api_version,
        "scopes": installation.scopes,
        "history": (
            "ALL_APPROVED_ORDERS"
            if "read_all_orders" in installation.scopes
            else "SHOPIFY_DEFAULT_ORDER_WINDOW"
        ),
    }


def _safe_sync_error(error: Exception) -> str:
    match = re.fullmatch(
        r"Shopify (customers|products|orders) bulk operation "
        r"(FAILED|CANCELED|EXPIRED|REJECTED): ([A-Z0-9_]+)",
        str(error),
    )
    if match is None:
        return "Read-only Shopify sync failed; inspect server-side diagnostics."
    object_type, status, error_code = match.groups()
    return f"Shopify {object_type} bulk operation {status}: {error_code}"
