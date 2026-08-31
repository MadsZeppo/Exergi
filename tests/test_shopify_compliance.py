from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from commercial_twin.shopify.compliance import current_document_contract, load_documents
from commercial_twin.shopify.retention import (
    DailyMaintenanceWorker,
    MaintenanceResult,
    MaintenanceSettings,
    _source_customer_candidates,
    build_maintenance_router,
)
from commercial_twin.shopify.webhooks import SqlPrivacyProcessor

ROOT = Path(__file__).resolve().parents[1]


def test_public_document_contract_is_versioned_complete_and_deterministic() -> None:
    first = current_document_contract()
    second = current_document_contract()
    documents = load_documents()

    assert first == second
    assert first[0] == documents["version"]
    assert set(first[1]) == {"terms", "privacy", "dpa", "subprocessors"}
    assert all(len(value) == 64 for value in first[1].values())
    assert documents["review_status"] == "FOUNDER_PREPARED_PENDING_LEGAL_REVIEW"
    assert "24 hours" in str(documents["privacy"])
    assert "30 days" in str(documents["privacy"])
    assert "90 days" in str(documents["privacy"])


def test_acceptance_is_idempotent_and_browser_never_supplies_merchant_id() -> None:
    backend = (ROOT / "src/commercial_twin/shopify/compliance.py").read_text()
    onboarding = (ROOT / "app/onboarding/onboarding-client.tsx").read_text()
    request_body = onboarding.split("async function acceptAgreements", 1)[1].split(
        "const authReady", 1
    )[0]

    assert "ON CONFLICT (merchant_id, agreement_version, clerk_subject_hash) DO NOTHING" in backend
    assert "body: JSON.stringify({ accepted: true, agreement_version:" in request_body
    assert "merchant_id" not in request_body


def test_cron_authentication_is_constant_time_and_fails_closed() -> None:
    worker = MagicMock()
    reconciliation = MagicMock()
    worker.run.return_value = MaintenanceResult(1, 2, {"oauth_nonces": 3})
    app = FastAPI()
    app.include_router(
        build_maintenance_router(
            worker,
            MaintenanceSettings("s" * 40),
            reconciliation=reconciliation,
        )
    )
    client = TestClient(app)

    assert client.post("/api/v1/maintenance/daily").status_code == 401
    assert client.post(
        "/api/v1/maintenance/daily", headers={"X-Exergi-Maintenance-Secret": "wrong"}
    ).status_code == 401
    accepted = client.post(
        "/api/v1/maintenance/daily",
        headers={"X-Exergi-Maintenance-Secret": "s" * 40},
    )
    assert accepted.json() == {
        "status": "COMPLETED",
        "tenants_processed": 1,
        "jobs_processed": 2,
        "rows_deleted": {"oauth_nonces": 3},
    }
    assert "s" * 40 not in accepted.text
    worker.run.assert_called_once_with()
    reconciliation.assert_called_once_with()


def test_retention_cutoffs_are_explicit_and_parameterized() -> None:
    connection = MagicMock()
    connection.execute.return_value.rowcount = 2
    now = datetime(2026, 8, 31, tzinfo=UTC)
    counts = DailyMaintenanceWorker._apply_cutoffs(
        connection, "00000000-0000-4000-8000-000000000001", now  # type: ignore[arg-type]
    )
    statements = "\n".join(str(call.args[0]) for call in connection.execute.call_args_list)

    assert counts == {
        "oauth_nonces": 2,
        "webhook_receipts": 2,
        "reconciled_raw_payloads": 2,
        "legacy_reconciled_raw_payloads": 2,
        "expired_privacy_exports": 2,
        "completed_privacy_jobs": 2,
    }
    assert "interval '24 hours'" in statements
    assert "interval '30 days'" in statements
    assert "interval '90 days'" in statements


def test_data_request_job_excludes_direct_customer_fields(monkeypatch: Any) -> None:
    processor = SqlPrivacyProcessor(MagicMock(), "p" * 40)
    queued: list[tuple[str, str, dict[str, Any]]] = []

    def capture(shop: str, kind: str, payload: dict[str, Any]) -> None:
        queued.append((shop, kind, payload))

    monkeypatch.setattr(processor, "_enqueue", capture)
    processor.data_request(
        "safe-shop.myshopify.com",
        {
            "customer": {"id": 42, "email": "private@example.test", "phone": "+451234"},
            "orders_requested": [7],
            "data_request": {"id": 9},
        },
    )
    serialized = str(queued)
    assert queued[0][1] == "SHOPIFY_CUSTOMER_DATA_EXPORT"
    assert "private@example.test" not in serialized
    assert "+451234" not in serialized


def test_redaction_and_shop_delete_cover_raw_and_analytical_records() -> None:
    privacy_source = (ROOT / "src/commercial_twin/shopify/webhooks.py").read_text()
    worker_source = (ROOT / "src/commercial_twin/shopify/retention.py").read_text()
    for table in (
        "raw_import_objects", "raw_source_records", "customer_identities",
        "customer_state_snapshots", "customer_daily_state", "behavior_events",
        "campaign_events", "experiment_assignments", "experiment_exposures",
        "experiment_outcomes",
    ):
        assert table in privacy_source
    for table in ("shops", "shop_connections", "orders", "customers", "raw_import_objects"):
        assert f"DELETE FROM {table}" in worker_source
    assert _source_customer_candidates("42") == ("42", "gid://shopify/Customer/42")


def test_mandatory_webhooks_and_daily_cron_are_declared() -> None:
    shopify_config = (ROOT / "shopify.app.toml").read_text()
    vercel_config = (ROOT / "vercel.json").read_text()
    for topic in ("customers/data_request", "customers/redact", "shop/redact", "app/uninstalled"):
        assert topic in shopify_config
    assert "/api/cron/retention" in vercel_config
