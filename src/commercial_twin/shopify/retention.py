"""Daily tenant-scoped retention and durable Shopify privacy-job processing."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from sqlalchemy import Connection, Engine, text

from commercial_twin.database_security import tenant_transaction

from .security import pseudonymize_customer

PRIVACY_JOB_TYPES = (
    "SHOPIFY_CUSTOMER_DATA_EXPORT",
    "SHOPIFY_CUSTOMER_REDACTION_AUDIT",
    "SHOPIFY_SHOP_HARD_DELETE",
    "SHOPIFY_RETENTION_REVIEW",
)


@dataclass(frozen=True)
class MaintenanceSettings:
    cron_secret: str

    @classmethod
    def from_env(cls) -> MaintenanceSettings:
        secret = os.environ.get("RETENTION_CRON_SECRET", "")
        if len(secret.encode()) < 32:
            raise RuntimeError("RETENTION_CRON_SECRET must contain at least 32 bytes")
        return cls(secret)


@dataclass
class MaintenanceResult:
    tenants_processed: int = 0
    jobs_processed: int = 0
    rows_deleted: dict[str, int] = field(default_factory=dict)


class DailyMaintenanceWorker:
    def __init__(self, engine: Engine, customer_pseudonym_key: str) -> None:
        if len(customer_pseudonym_key.encode()) < 32:
            raise ValueError("customer pseudonym key must contain at least 32 bytes")
        self.engine = engine
        self.customer_pseudonym_key = customer_pseudonym_key

    def run(self, *, now: datetime | None = None) -> MaintenanceResult:
        current = now or datetime.now(UTC)
        result = MaintenanceResult()
        for merchant_id in self._registered_merchants():
            tenant_result = self._run_tenant(merchant_id, current)
            result.tenants_processed += 1
            result.jobs_processed += tenant_result.jobs_processed
            for category, count in tenant_result.rows_deleted.items():
                result.rows_deleted[category] = result.rows_deleted.get(category, 0) + count
        return result

    def _registered_merchants(self) -> tuple[UUID, ...]:
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.maintenance_mode', 'retention-v1', true)")
            )
            rows = connection.execute(
                text("SELECT merchant_id FROM maintenance_tenants ORDER BY merchant_id")
            ).scalars()
            return tuple(rows)

    def _run_tenant(self, merchant_id: UUID, now: datetime) -> MaintenanceResult:
        run_id = uuid4()
        result = MaintenanceResult(tenants_processed=1)
        try:
            with tenant_transaction(self.engine, merchant_id) as connection:
                connection.execute(
                    text("""
                    INSERT INTO compliance_runs (id, merchant_id, started_at, status)
                    VALUES (:id, :merchant_id, :started_at, 'RUNNING')
                    """),
                    {"id": run_id, "merchant_id": merchant_id, "started_at": now},
                )
                result.rows_deleted = self._apply_cutoffs(connection, merchant_id, now)
                jobs = (
                    connection.execute(
                        text("""
                        SELECT id, job_type, payload FROM jobs
                        WHERE merchant_id = :merchant_id AND status = 'PENDING'
                          AND available_at <= :now AND job_type = ANY(:job_types)
                        ORDER BY available_at, id
                        FOR UPDATE SKIP LOCKED LIMIT 100
                        """),
                        {
                            "merchant_id": merchant_id,
                            "now": now,
                            "job_types": list(PRIVACY_JOB_TYPES),
                        },
                    )
                    .mappings()
                    .all()
                )
                for job in jobs:
                    self._process_job(connection, merchant_id, job, now, result)
                connection.execute(
                    text("""
                    UPDATE compliance_runs SET completed_at = :now, status = 'COMPLETED',
                        rows_deleted_json = CAST(:counts AS jsonb),
                        jobs_processed = :jobs
                    WHERE id = :id AND merchant_id = :merchant_id
                    """),
                    {
                        "id": run_id,
                        "merchant_id": merchant_id,
                        "now": now,
                        "counts": json.dumps(result.rows_deleted, sort_keys=True),
                        "jobs": result.jobs_processed,
                    },
                )
        except Exception as exc:
            with tenant_transaction(self.engine, merchant_id) as connection:
                connection.execute(
                    text("""
                    INSERT INTO compliance_runs
                        (id, merchant_id, started_at, completed_at, status, error_summary)
                    VALUES (:id, :merchant_id, :started_at, :completed_at, 'FAILED', :error)
                    ON CONFLICT (id) DO UPDATE SET completed_at = EXCLUDED.completed_at,
                        status = 'FAILED', error_summary = EXCLUDED.error_summary
                    """),
                    {
                        "id": run_id,
                        "merchant_id": merchant_id,
                        "started_at": now,
                        "completed_at": datetime.now(UTC),
                        "error": type(exc).__name__,
                    },
                )
            return result
        return result

    @staticmethod
    def _apply_cutoffs(
        connection: Connection, merchant_id: UUID, now: datetime
    ) -> dict[str, int]:
        legacy_raw_scope = """
            SELECT raw.id FROM raw_source_records raw
            JOIN sync_runs sync ON sync.id = raw.ingestion_run_id
            WHERE raw.merchant_id = :merchant_id AND sync.merchant_id = :merchant_id
              AND sync.status = 'COMPLETED'
              AND raw.observed_at < :now - interval '90 days'
        """
        for table in ("orders", "order_lines", "refunds", "behavior_events"):
            connection.execute(
                text(
                    f"UPDATE {table} SET raw_source_record_id = NULL "
                    f"WHERE merchant_id = :merchant_id AND raw_source_record_id IN "
                    f"({legacy_raw_scope})"
                ),
                {"merchant_id": merchant_id, "now": now},
            )
        statements = {
            "oauth_nonces": """
                DELETE FROM shopify_oauth_nonces
                WHERE merchant_id = :merchant_id
                  AND created_at < :now - interval '24 hours'
            """,
            "webhook_receipts": """
                DELETE FROM shopify_webhook_receipts
                WHERE merchant_id = :merchant_id
                  AND received_at < :now - interval '30 days'
            """,
            "reconciled_raw_payloads": """
                DELETE FROM raw_import_objects raw
                USING sync_runs sync
                WHERE raw.merchant_id = :merchant_id
                  AND raw.sync_run_id = sync.id
                  AND sync.merchant_id = :merchant_id
                  AND sync.status = 'COMPLETED'
                  AND raw.ingested_at < :now - interval '90 days'
            """,
            "legacy_reconciled_raw_payloads": f"""
                DELETE FROM raw_source_records
                WHERE merchant_id = :merchant_id AND id IN ({legacy_raw_scope})
            """,
            "expired_privacy_exports": """
                DELETE FROM privacy_exports
                WHERE merchant_id = :merchant_id AND expires_at <= :now
            """,
            "completed_privacy_jobs": """
                DELETE FROM jobs
                WHERE merchant_id = :merchant_id AND status = 'COMPLETED'
                  AND completed_at < :now - interval '30 days'
                  AND job_type = ANY(:job_types)
            """,
        }
        counts: dict[str, int] = {}
        for category, statement in statements.items():
            parameters: dict[str, Any] = {"merchant_id": merchant_id, "now": now}
            if category == "completed_privacy_jobs":
                parameters["job_types"] = list(PRIVACY_JOB_TYPES)
            rowcount = connection.execute(text(statement), parameters).rowcount
            counts[category] = max(0, rowcount or 0)
        return counts

    def _process_job(
        self,
        connection: Connection,
        merchant_id: UUID,
        job: Any,
        now: datetime,
        result: MaintenanceResult,
    ) -> None:
        payload = job["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload = self._normalize_legacy_payload(connection, merchant_id, payload)
        connection.execute(
            text("""
            UPDATE jobs SET status = 'RUNNING', locked_at = :now, attempts = attempts + 1
            WHERE id = :id AND merchant_id = :merchant_id
            """),
            {"id": job["id"], "merchant_id": merchant_id, "now": now},
        )
        try:
            with connection.begin_nested():
                if job["job_type"] == "SHOPIFY_CUSTOMER_DATA_EXPORT":
                    self._create_export(connection, merchant_id, job["id"], payload, now)
                elif job["job_type"] in {
                    "SHOPIFY_SHOP_HARD_DELETE",
                    "SHOPIFY_RETENTION_REVIEW",
                }:
                    if job["job_type"] == "SHOPIFY_RETENTION_REVIEW" and self._is_reconnected(
                        connection, merchant_id, payload
                    ):
                        pass
                    else:
                        self._hard_delete_shop(connection, merchant_id, payload, result)
            connection.execute(
                text("""
                UPDATE jobs SET status = 'COMPLETED', completed_at = :now,
                    locked_at = NULL, error = NULL, payload = '{}'
                WHERE id = :id AND merchant_id = :merchant_id
                """),
                {"id": job["id"], "merchant_id": merchant_id, "now": now},
            )
            result.jobs_processed += 1
        except Exception as exc:
            connection.execute(
                text("""
                UPDATE jobs SET status = CASE WHEN attempts >= 3 THEN 'FAILED' ELSE 'PENDING' END,
                    locked_at = NULL, error = :error,
                    available_at = :now + interval '1 day'
                WHERE id = :id AND merchant_id = :merchant_id
                """),
                {
                    "id": job["id"],
                    "merchant_id": merchant_id,
                    "now": now,
                    "error": type(exc).__name__,
                },
            )

    @staticmethod
    def _normalize_legacy_payload(
        connection: Connection, merchant_id: UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        normalized = dict(payload)
        customer = normalized.get("customer")
        request = normalized.get("data_request")
        if isinstance(customer, dict):
            normalized.setdefault("customer_id", str(customer.get("id", "")))
        if isinstance(request, dict):
            normalized.setdefault("request_id", str(request.get("id", "")))
        normalized.setdefault("order_ids", normalized.get("orders_requested", []))
        raw_shop_id = normalized.get("shop_id")
        try:
            normalized["shop_id"] = str(UUID(str(raw_shop_id)))
            return normalized
        except (ValueError, TypeError, AttributeError):
            pass
        shop_domain = str(normalized.get("shop") or normalized.get("shop_domain") or "")
        row = connection.execute(
            text("""
            SELECT shop_id FROM shop_connections
            WHERE merchant_id = :merchant_id
              AND (:shop_domain = '' OR shop_domain = :shop_domain)
            ORDER BY installed_at DESC LIMIT 1
            """),
            {"merchant_id": merchant_id, "shop_domain": shop_domain},
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("privacy job has no installed shop route")
        normalized["shop_id"] = str(row)
        return normalized

    @staticmethod
    def _is_reconnected(
        connection: Connection, merchant_id: UUID, payload: dict[str, Any]
    ) -> bool:
        return bool(
            connection.execute(
                text("""
                SELECT EXISTS (
                  SELECT 1 FROM shop_connections
                  WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                    AND status = 'CONNECTED' AND encrypted_access_token <> ''
                )
                """),
                {"merchant_id": merchant_id, "shop_id": UUID(str(payload["shop_id"]))},
            ).scalar_one()
        )

    def _create_export(
        self,
        connection: Connection,
        merchant_id: UUID,
        job_id: UUID,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        shop_id = UUID(str(payload["shop_id"]))
        customer_ids = _source_customer_candidates(str(payload.get("customer_id", "")))
        pseudonyms = [
            pseudonymize_customer(shop_id, value, self.customer_pseudonym_key)
            for value in customer_ids
            if value
        ]
        customers = (
            connection.execute(
                text("""
                SELECT id, pseudonymous_customer_key, first_seen_at, last_seen_at
                FROM customers WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                  AND pseudonymous_customer_key = ANY(:pseudonyms)
                """),
                {
                    "merchant_id": merchant_id,
                    "shop_id": shop_id,
                    "pseudonyms": pseudonyms,
                },
            )
            .mappings()
            .all()
        )
        internal_customer_ids = [row["id"] for row in customers]
        order_ids = _source_order_candidates(payload.get("order_ids", []))
        orders = (
            connection.execute(
                text("""
                SELECT external_order_id, ordered_at, currency, gross_item_sales,
                       line_discounts, shipping_revenue, net_sales
                FROM orders WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                  AND external_order_id = ANY(:order_ids)
                ORDER BY ordered_at
                """),
                {"merchant_id": merchant_id, "shop_id": shop_id, "order_ids": order_ids},
            )
            .mappings()
            .all()
        )
        derived: dict[str, list[dict[str, Any]]] = {}
        customer_queries = {
            "customer_daily_state": """
                SELECT as_of, state_version, state_json FROM customer_daily_state
                WHERE merchant_id=:merchant_id AND shop_id=:shop_id
                  AND customer_id=ANY(:customer_ids) ORDER BY as_of
            """,
            "customer_state_snapshots": """
                SELECT as_of, state_version, observed_state_json, predictive_state_json,
                       support_json, uncertainty_json FROM customer_state_snapshots
                WHERE merchant_id=:merchant_id AND customer_id=ANY(:customer_ids)
                ORDER BY as_of
            """,
            "behavior_events": """
                SELECT event_type, occurred_at, properties_jsonb FROM behavior_events
                WHERE merchant_id=:merchant_id AND customer_id=ANY(:customer_ids)
                ORDER BY occurred_at
            """,
            "campaign_events": """
                SELECT event_type, occurred_at, properties_jsonb FROM campaign_events
                WHERE merchant_id=:merchant_id AND customer_id=ANY(:customer_ids)
                ORDER BY occurred_at
            """,
            "experiment_assignments": """
                SELECT experiment_id, arm_id, assigned_at, assignment_probability, stratum
                FROM experiment_assignments
                WHERE merchant_id=:merchant_id AND customer_id=ANY(:customer_ids)
                ORDER BY assigned_at
            """,
            "experiment_exposures": """
                SELECT experiment_id, arm_id, exposed_at, provider
                FROM experiment_exposures
                WHERE merchant_id=:merchant_id AND customer_id=ANY(:customer_ids)
                ORDER BY exposed_at
            """,
            "experiment_outcomes": """
                SELECT experiment_id, window_start, window_end, purchase, order_count,
                       gross_sales, net_sales, refunds, returns, contribution_profit
                FROM experiment_outcomes
                WHERE merchant_id=:merchant_id AND customer_id=ANY(:customer_ids)
                ORDER BY window_start
            """,
        }
        query_parameters = {
            "merchant_id": merchant_id,
            "shop_id": shop_id,
            "customer_ids": internal_customer_ids,
        }
        for category, query in customer_queries.items():
            rows = connection.execute(text(query), query_parameters).mappings().all()
            derived[category] = [dict(row) for row in rows]
        export = {
            "categories": [
                "pseudonymous_customer_state",
                "order_economics",
                "derived_customer_records",
            ],
            "customers": [
                {key: value for key, value in dict(row).items() if key != "id"}
                for row in customers
            ],
            "orders": [dict(row) for row in orders],
            "derived_records": derived,
            "generated_at": now.isoformat(),
        }
        connection.execute(
            text("""
            INSERT INTO privacy_exports
                (id, merchant_id, shop_id, request_job_id, status, result_json,
                 created_at, expires_at)
            VALUES (:id, :merchant_id, :shop_id, :job_id, 'READY',
                    CAST(:result AS jsonb), :now, :now + interval '30 days')
            ON CONFLICT (request_job_id) DO NOTHING
            """),
            {
                "id": uuid4(),
                "merchant_id": merchant_id,
                "shop_id": shop_id,
                "job_id": job_id,
                "result": json.dumps(export, sort_keys=True, default=str),
                "now": now,
            },
        )

    @staticmethod
    def _hard_delete_shop(
        connection: Connection,
        merchant_id: UUID,
        payload: dict[str, Any],
        result: MaintenanceResult,
    ) -> None:
        shop_id = UUID(str(payload["shop_id"]))
        params = {"merchant_id": merchant_id, "shop_id": shop_id}
        customer_scope = """
            SELECT id FROM customers
            WHERE merchant_id = :merchant_id AND shop_id = :shop_id
        """
        statements = (
            """DELETE FROM verified_profit_ledger
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM matured_outcomes
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM assignments
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM experiment_contracts
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM prediction_ledger
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM decision_cards
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM decision_opportunities
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM data_quality_results
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM economic_assumptions
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM company_daily_state
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            f"""DELETE FROM experiment_outcomes
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            f"""DELETE FROM experiment_exposures
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            f"""DELETE FROM experiment_assignments
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            f"""DELETE FROM campaign_events
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            f"""DELETE FROM behavior_events
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            f"""DELETE FROM customer_state_snapshots
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            f"""DELETE FROM customer_daily_state
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            f"""DELETE FROM customer_identities
                 WHERE merchant_id=:merchant_id AND customer_id IN ({customer_scope})""",
            """UPDATE orders SET customer_id=NULL, deletion_status='SHOP_REDACTED'
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM customers
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM payment_transactions
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM fulfillments
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM returns
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM discounts
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM return_lines WHERE order_line_id IN
               (SELECT id FROM order_lines
                WHERE merchant_id=:merchant_id AND shop_id=:shop_id)""",
            """DELETE FROM refunds
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM order_lines
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM orders
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM behavior_events
               WHERE merchant_id=:merchant_id AND (
                 product_id IN (SELECT id FROM products
                   WHERE merchant_id=:merchant_id AND shop_id=:shop_id)
                 OR variant_id IN (SELECT id FROM variants
                   WHERE merchant_id=:merchant_id AND shop_id=:shop_id))""",
            """DELETE FROM variants
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM products
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM shopify_webhook_receipts
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM raw_import_objects
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM privacy_exports
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM raw_source_records
               WHERE merchant_id=:merchant_id AND connection_id IN
                 (SELECT id FROM data_connections WHERE merchant_id=:merchant_id
                  AND external_account_id=(SELECT shop_domain FROM shops WHERE id=:shop_id))""",
            """DELETE FROM sync_runs
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM shopify_oauth_nonces
               WHERE merchant_id=:merchant_id AND shop_domain=
                 (SELECT shop_domain FROM shops WHERE id=:shop_id)""",
            """DELETE FROM shop_connections
               WHERE merchant_id=:merchant_id AND shop_id=:shop_id""",
            """DELETE FROM data_connections
               WHERE merchant_id=:merchant_id AND external_account_id=
                 (SELECT shop_domain FROM shops WHERE id=:shop_id)""",
            """DELETE FROM shops
               WHERE merchant_id=:merchant_id AND id=:shop_id""",
        )
        deleted = 0
        for statement in statements:
            deleted += max(0, connection.execute(text(statement), params).rowcount or 0)
        result.rows_deleted["shop_hard_delete"] = (
            result.rows_deleted.get("shop_hard_delete", 0) + deleted
        )


def build_maintenance_router(
    worker: DailyMaintenanceWorker,
    settings: MaintenanceSettings,
    reconciliation: Callable[[], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/maintenance", tags=["internal-maintenance"])

    @router.post("/daily")
    def daily(
        background_tasks: BackgroundTasks,
        x_exergi_maintenance_secret: str | None = Header(default=None),
    ) -> dict[str, Any]:
        supplied = (x_exergi_maintenance_secret or "").encode()
        expected = settings.cron_secret.encode()
        if not hmac.compare_digest(
            hashlib.sha256(supplied).digest(), hashlib.sha256(expected).digest()
        ):
            raise HTTPException(status_code=401, detail="invalid maintenance authentication")
        result = worker.run()
        if reconciliation is not None:
            background_tasks.add_task(reconciliation)
        return {
            "status": "COMPLETED",
            "tenants_processed": result.tenants_processed,
            "jobs_processed": result.jobs_processed,
            "rows_deleted": result.rows_deleted,
        }

    return router


def _source_customer_candidates(source_id: str) -> tuple[str, ...]:
    if not source_id:
        return ()
    if source_id.startswith("gid://"):
        return (source_id, source_id.rsplit("/", 1)[-1])
    return (source_id, f"gid://shopify/Customer/{source_id}")


def _source_order_candidates(values: Any) -> list[str]:
    candidates: list[str] = []
    for raw in values if isinstance(values, list) else []:
        value = str(raw)
        candidates.append(value)
        if not value.startswith("gid://"):
            candidates.append(f"gid://shopify/Order/{value}")
    return candidates
