# ruff: noqa: E501
"""Versioned agreements, privacy exports and tenant-scoped compliance operations."""

from __future__ import annotations

from alembic import op

revision = "0005_compliance_retention"
down_revision = "0004_shops_tenant_domain_unique"
branch_labels = None
depends_on = None

TENANT = "nullif(current_setting('app.merchant_id', true), '')::uuid"
MAINTENANCE = "current_setting('app.maintenance_mode', true) = 'retention-v1'"

TABLES = (
    "merchant_agreement_acceptances",
    "maintenance_tenants",
    "compliance_runs",
    "privacy_exports",
)


def upgrade() -> None:
    op.execute("""
    CREATE TABLE merchant_agreement_acceptances (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      organization_id uuid NOT NULL REFERENCES organizations(id),
      merchant_id uuid NOT NULL REFERENCES merchants(id),
      agreement_version text NOT NULL,
      document_hashes jsonb NOT NULL,
      clerk_subject_hash text NOT NULL,
      accepted_at timestamptz NOT NULL DEFAULT now(),
      request_ip_hash text NOT NULL,
      user_agent_hash text NOT NULL,
      request_origin text NOT NULL,
      UNIQUE (merchant_id, agreement_version, clerk_subject_hash)
    );
    CREATE TABLE maintenance_tenants (
      merchant_id uuid PRIMARY KEY REFERENCES merchants(id),
      registered_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE compliance_runs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      merchant_id uuid NOT NULL REFERENCES merchants(id),
      started_at timestamptz NOT NULL,
      completed_at timestamptz,
      status text NOT NULL CHECK (status IN ('RUNNING','COMPLETED','FAILED')),
      rows_deleted_json jsonb NOT NULL DEFAULT '{}',
      jobs_processed integer NOT NULL DEFAULT 0,
      error_summary text
    );
    CREATE TABLE privacy_exports (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL,
      request_job_id uuid NOT NULL UNIQUE,
      status text NOT NULL CHECK (status IN ('READY','EXPIRED')),
      result_json jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL
    );
    CREATE INDEX compliance_runs_latest ON compliance_runs (merchant_id, started_at DESC);
    CREATE INDEX privacy_exports_expiry ON privacy_exports (merchant_id, expires_at);
    """)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            f"USING (merchant_id = {TENANT}) WITH CHECK (merchant_id = {TENANT})"
        )
    op.execute(
        "CREATE POLICY maintenance_tenants_worker_select ON maintenance_tenants "
        f"FOR SELECT USING ({MAINTENANCE})"
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
