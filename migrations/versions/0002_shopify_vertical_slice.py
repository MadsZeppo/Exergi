# ruff: noqa: E501
"""Production-shaped read-only Shopify vertical slice.

Revision ID: 0002_shopify_vertical_slice
Revises: 0001_merchant_validation_v1
"""

from __future__ import annotations

from alembic import op

revision = "0002_shopify_vertical_slice"
down_revision = "0001_merchant_validation_v1"
branch_labels = None
depends_on = None


NEW_TABLES = (
    "shops",
    "shop_connections",
    "shopify_oauth_nonces",
    "shopify_webhook_receipts",
    "raw_import_objects",
    "discounts",
    "returns",
    "fulfillments",
    "payment_transactions",
    "customer_daily_state",
    "company_daily_state",
    "economic_assumptions",
    "data_quality_results",
    "decision_opportunities",
    "decision_cards",
    "prediction_ledger",
    "experiment_contracts",
    "assignments",
    "matured_outcomes",
    "verified_profit_ledger",
)


def upgrade() -> None:
    op.execute("""
    CREATE TABLE shops (
      id uuid PRIMARY KEY, merchant_id uuid NOT NULL REFERENCES merchants(id),
      source_shop_id text, shop_domain text NOT NULL, name text, currency char(3),
      iana_timezone text, source_version text NOT NULL, occurred_at timestamptz,
      observed_at timestamptz NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
      deletion_status text NOT NULL DEFAULT 'ACTIVE',
      UNIQUE (shop_domain), UNIQUE (merchant_id, source_shop_id)
    );
    CREATE TABLE shop_connections (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id),
      merchant_id uuid NOT NULL REFERENCES merchants(id), shop_id uuid NOT NULL,
      shop_domain text NOT NULL, encrypted_access_token text NOT NULL,
      encrypted_refresh_token text, scopes_json jsonb NOT NULL,
      api_version text NOT NULL, access_token_expires_at timestamptz,
      refresh_token_expires_at timestamptz, status text NOT NULL,
      installed_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
      UNIQUE (shop_domain)
    );
    CREATE TABLE shopify_oauth_nonces (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_domain text NOT NULL, nonce_hash text NOT NULL, expires_at timestamptz NOT NULL,
      consumed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (merchant_id, shop_domain, nonce_hash)
    );
    CREATE TABLE shopify_webhook_receipts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, shop_domain text NOT NULL, webhook_id text NOT NULL,
      topic text NOT NULL, payload_hash text NOT NULL, received_at timestamptz NOT NULL,
      processed_at timestamptz, UNIQUE (shop_domain, webhook_id)
    );
    CREATE TABLE raw_import_objects (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, sync_run_id uuid, object_type text NOT NULL, source_id text NOT NULL,
      source_updated_at timestamptz, source_version text NOT NULL, payload_json jsonb NOT NULL,
      payload_hash text NOT NULL, occurred_at timestamptz, observed_at timestamptz NOT NULL,
      ingested_at timestamptz NOT NULL, deletion_status text NOT NULL DEFAULT 'ACTIVE',
      UNIQUE (shop_id, object_type, source_id, payload_hash)
    );
    CREATE TABLE discounts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, order_id uuid NOT NULL REFERENCES orders(id), order_line_id uuid REFERENCES order_lines(id),
      source_id text NOT NULL, amount numeric NOT NULL, currency char(3) NOT NULL,
      discount_type text, occurred_at timestamptz NOT NULL, observed_at timestamptz NOT NULL,
      ingested_at timestamptz NOT NULL DEFAULT now(), source_version text NOT NULL,
      deletion_status text NOT NULL DEFAULT 'ACTIVE', UNIQUE (shop_id, source_id)
    );
    CREATE TABLE returns (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, order_id uuid NOT NULL REFERENCES orders(id), source_id text NOT NULL,
      status text, quantity integer NOT NULL DEFAULT 0, refund_amount numeric,
      currency char(3), occurred_at timestamptz NOT NULL, observed_at timestamptz NOT NULL,
      ingested_at timestamptz NOT NULL DEFAULT now(), source_version text NOT NULL,
      deletion_status text NOT NULL DEFAULT 'ACTIVE', UNIQUE (shop_id, source_id)
    );
    CREATE TABLE fulfillments (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, order_id uuid NOT NULL REFERENCES orders(id), source_id text NOT NULL,
      status text, occurred_at timestamptz, observed_at timestamptz NOT NULL,
      ingested_at timestamptz NOT NULL DEFAULT now(), source_version text NOT NULL,
      deletion_status text NOT NULL DEFAULT 'ACTIVE', UNIQUE (shop_id, source_id)
    );
    CREATE TABLE payment_transactions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, order_id uuid REFERENCES orders(id), source_id text NOT NULL,
      kind text, status text, gateway text, amount numeric NOT NULL, fee_amount numeric,
      currency char(3) NOT NULL, occurred_at timestamptz NOT NULL, observed_at timestamptz NOT NULL,
      ingested_at timestamptz NOT NULL DEFAULT now(), source_version text NOT NULL,
      deletion_status text NOT NULL DEFAULT 'ACTIVE', UNIQUE (shop_id, source_id)
    );
    CREATE TABLE customer_daily_state (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, customer_id uuid NOT NULL REFERENCES customers(id), as_of timestamptz NOT NULL,
      state_version text NOT NULL, state_json jsonb NOT NULL, state_hash text NOT NULL,
      observed_at timestamptz NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (shop_id, customer_id, as_of, state_version)
    );
    CREATE TABLE company_daily_state (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, as_of timestamptz NOT NULL, state_version text NOT NULL,
      state_json jsonb NOT NULL, state_hash text NOT NULL, observed_at timestamptz NOT NULL,
      ingested_at timestamptz NOT NULL DEFAULT now(), UNIQUE (shop_id, as_of, state_version)
    );
    CREATE TABLE economic_assumptions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, version text NOT NULL, valid_from timestamptz NOT NULL,
      valid_to timestamptz, assumptions_json jsonb NOT NULL, created_by text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (shop_id, version)
    );
    CREATE TABLE data_quality_results (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, sync_run_id uuid, as_of timestamptz NOT NULL, status text NOT NULL,
      completeness_json jsonb NOT NULL, reconciliation_json jsonb NOT NULL,
      reason_codes_json jsonb NOT NULL, result_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (shop_id, result_hash)
    );
    CREATE TABLE decision_opportunities (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, as_of timestamptz NOT NULL, opportunity_type text NOT NULL,
      observation_json jsonb NOT NULL, evidence_authority text NOT NULL, source_state_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE decision_cards (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, opportunity_id uuid REFERENCES decision_opportunities(id),
      recommendation text NOT NULL CHECK (recommendation IN ('TEST','AVOID','NOT_ENOUGH_EVIDENCE','BAU')),
      card_json jsonb NOT NULL, evidence_authority text NOT NULL, card_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (shop_id, card_hash)
    );
    CREATE TABLE prediction_ledger (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, decision_card_id uuid REFERENCES decision_cards(id), frozen_at timestamptz NOT NULL,
      prediction_json jsonb NOT NULL, maturity_at timestamptz NOT NULL, status text NOT NULL,
      prediction_hash text NOT NULL UNIQUE
    );
    CREATE TABLE experiment_contracts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, decision_card_id uuid REFERENCES decision_cards(id), status text NOT NULL,
      contract_json jsonb NOT NULL, frozen_at timestamptz, contract_hash text UNIQUE
    );
    CREATE TABLE assignments (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, experiment_contract_id uuid NOT NULL REFERENCES experiment_contracts(id),
      pseudonymous_unit_key text NOT NULL, arm text NOT NULL, propensity numeric NOT NULL,
      assigned_at timestamptz NOT NULL, assignment_hash text NOT NULL,
      UNIQUE (experiment_contract_id, pseudonymous_unit_key)
    );
    CREATE TABLE matured_outcomes (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, assignment_id uuid NOT NULL REFERENCES assignments(id),
      matured_at timestamptz NOT NULL, outcome_json jsonb NOT NULL, authority text NOT NULL,
      outcome_hash text NOT NULL UNIQUE
    );
    CREATE TABLE verified_profit_ledger (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id),
      shop_id uuid NOT NULL, experiment_contract_id uuid NOT NULL REFERENCES experiment_contracts(id),
      recorded_at timestamptz NOT NULL, incremental_profit numeric, currency char(3),
      authority text NOT NULL, uncertainty_json jsonb NOT NULL, result_hash text NOT NULL UNIQUE
    );
    """)
    op.execute("""
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS shop_id uuid;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS deletion_status text NOT NULL DEFAULT 'ACTIVE';
    ALTER TABLE products ADD COLUMN IF NOT EXISTS shop_id uuid;
    ALTER TABLE products ADD COLUMN IF NOT EXISTS observed_at timestamptz;
    ALTER TABLE products ADD COLUMN IF NOT EXISTS ingested_at timestamptz NOT NULL DEFAULT now();
    ALTER TABLE products ADD COLUMN IF NOT EXISTS source_version text;
    ALTER TABLE products ADD COLUMN IF NOT EXISTS deletion_status text NOT NULL DEFAULT 'ACTIVE';
    ALTER TABLE variants ADD COLUMN IF NOT EXISTS shop_id uuid;
    ALTER TABLE variants ADD COLUMN IF NOT EXISTS observed_at timestamptz;
    ALTER TABLE variants ADD COLUMN IF NOT EXISTS ingested_at timestamptz NOT NULL DEFAULT now();
    ALTER TABLE variants ADD COLUMN IF NOT EXISTS source_version text;
    ALTER TABLE variants ADD COLUMN IF NOT EXISTS deletion_status text NOT NULL DEFAULT 'ACTIVE';
    ALTER TABLE orders ADD COLUMN IF NOT EXISTS shop_id uuid;
    ALTER TABLE orders ADD COLUMN IF NOT EXISTS occurred_at timestamptz;
    ALTER TABLE orders ADD COLUMN IF NOT EXISTS observed_at timestamptz;
    ALTER TABLE orders ADD COLUMN IF NOT EXISTS ingested_at timestamptz NOT NULL DEFAULT now();
    ALTER TABLE orders ADD COLUMN IF NOT EXISTS source_version text;
    ALTER TABLE orders ADD COLUMN IF NOT EXISTS deletion_status text NOT NULL DEFAULT 'ACTIVE';
    ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS shop_id uuid;
    ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS observed_at timestamptz;
    ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS ingested_at timestamptz NOT NULL DEFAULT now();
    ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS source_version text;
    ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS deletion_status text NOT NULL DEFAULT 'ACTIVE';
    ALTER TABLE refunds ADD COLUMN IF NOT EXISTS shop_id uuid;
    ALTER TABLE refunds ADD COLUMN IF NOT EXISTS observed_at timestamptz;
    ALTER TABLE refunds ADD COLUMN IF NOT EXISTS ingested_at timestamptz NOT NULL DEFAULT now();
    ALTER TABLE refunds ADD COLUMN IF NOT EXISTS source_version text;
    ALTER TABLE refunds ADD COLUMN IF NOT EXISTS deletion_status text NOT NULL DEFAULT 'ACTIVE';
    ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS shop_id uuid;
    ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS checkpoint_json jsonb NOT NULL DEFAULT '{}';
    CREATE INDEX raw_import_resume ON raw_import_objects (shop_id, sync_run_id, object_type, ingested_at);
    CREATE INDEX customer_daily_asof ON customer_daily_state (shop_id, customer_id, as_of DESC);
    CREATE INDEX company_daily_asof ON company_daily_state (shop_id, as_of DESC);
    """)
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} USING "
            "(merchant_id = nullif(current_setting('app.merchant_id', true), '')::uuid) "
            "WITH CHECK (merchant_id = nullif(current_setting('app.merchant_id', true), '')::uuid)"
        )
    # Shopify authenticates webhooks before this narrow lookup. It exposes only the connection
    # matching the transaction-local canonical shop domain; all writes still require merchant_id.
    op.execute(
        "CREATE POLICY shop_connections_webhook_route_policy ON shop_connections "
        "FOR SELECT USING (shop_domain = nullif(current_setting('app.shop_domain', true), ''))"
    )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for table in ("customers", "products", "variants", "orders", "order_lines", "refunds"):
        for column in (
            "shop_id",
            "observed_at",
            "ingested_at",
            "source_version",
            "deletion_status",
        ):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS occurred_at")
    op.execute("ALTER TABLE sync_runs DROP COLUMN IF EXISTS checkpoint_json")
    op.execute("ALTER TABLE sync_runs DROP COLUMN IF EXISTS shop_id")
