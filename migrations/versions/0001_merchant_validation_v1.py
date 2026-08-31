# ruff: noqa: E501
"""Merchant Validation V1 PostgreSQL schema and tenant policies."""

from __future__ import annotations

from alembic import op

revision = "0001_merchant_validation_v1"
down_revision = None
branch_labels = None
depends_on = None


TABLES = (
    "organizations",
    "merchants",
    "data_connections",
    "sync_runs",
    "raw_source_records",
    "customers",
    "customer_identities",
    "products",
    "variants",
    "orders",
    "order_lines",
    "refunds",
    "return_lines",
    "behavior_events",
    "campaigns",
    "campaign_events",
    "cost_records",
    "data_health_runs",
    "data_health_checks",
    "customer_state_snapshots",
    "population_state_snapshots",
    "model_training_runs",
    "opportunities",
    "opportunity_evidence",
    "action_candidates",
    "experiments",
    "experiment_arms",
    "experiment_assignments",
    "experiment_exposures",
    "experiment_outcomes",
    "experiment_results",
    "merchant_learning_records",
    "jobs",
    "audit_log",
)

TENANT_SETTING = "nullif(current_setting('app.merchant_id', true), '')::uuid"

# The value is the tenant-bearing column on the policy's target table. Keeping this mapping
# explicit makes schema/policy drift testable instead of assuming every table has merchant_id.
POLICY_TARGET_COLUMNS = {
    **{table: "merchant_id" for table in TABLES},
    "organizations": "id",
    "merchants": "id",
    "data_health_checks": "data_health_run_id",
    "experiment_arms": "experiment_id",
}


def tenant_predicate(table: str) -> str:
    if table == "organizations":
        return (
            "EXISTS (SELECT 1 FROM merchants tenant_merchant "
            "WHERE tenant_merchant.organization_id = organizations.id "
            f"AND tenant_merchant.id = {TENANT_SETTING})"
        )
    if table == "merchants":
        return f"id = {TENANT_SETTING}"
    if table == "data_health_checks":
        return (
            "EXISTS (SELECT 1 FROM data_health_runs tenant_health_run "
            "WHERE tenant_health_run.id = data_health_checks.data_health_run_id "
            f"AND tenant_health_run.merchant_id = {TENANT_SETTING})"
        )
    if table == "experiment_arms":
        return (
            "EXISTS (SELECT 1 FROM experiments tenant_experiment "
            "WHERE tenant_experiment.id = experiment_arms.experiment_id "
            f"AND tenant_experiment.merchant_id = {TENANT_SETTING})"
        )
    return f"merchant_id = {TENANT_SETTING}"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""
    CREATE TABLE organizations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE merchants (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id), name text NOT NULL, slug text NOT NULL UNIQUE, timezone text NOT NULL, currency char(3) NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE data_connections (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), provider text NOT NULL, status text NOT NULL, external_account_id text, api_version text, encrypted_secret_reference text, scopes_json jsonb NOT NULL DEFAULT '{}', last_successful_sync_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE sync_runs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), connection_id uuid NOT NULL REFERENCES data_connections(id), sync_type text NOT NULL, started_at timestamptz NOT NULL, completed_at timestamptz, status text NOT NULL, cursor_start text, cursor_end text, source_rows bigint NOT NULL DEFAULT 0, accepted_rows bigint NOT NULL DEFAULT 0, rejected_rows bigint NOT NULL DEFAULT 0, duplicate_rows bigint NOT NULL DEFAULT 0, error_summary text);
    CREATE TABLE raw_source_records (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), connection_id uuid NOT NULL REFERENCES data_connections(id), provider text NOT NULL, source_object_type text NOT NULL, source_object_id text NOT NULL, source_updated_at timestamptz, observed_at timestamptz NOT NULL, payload_jsonb jsonb NOT NULL, payload_hash text NOT NULL, ingestion_run_id uuid REFERENCES sync_runs(id), UNIQUE (merchant_id, provider, source_object_type, source_object_id, payload_hash));
    CREATE TABLE customers (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), pseudonymous_customer_key text NOT NULL, first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (merchant_id, pseudonymous_customer_key));
    CREATE TABLE customer_identities (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), customer_id uuid NOT NULL REFERENCES customers(id), provider text NOT NULL, external_customer_id_hash text NOT NULL, encrypted_external_reference text, valid_from timestamptz NOT NULL, valid_to timestamptz, UNIQUE (merchant_id, provider, external_customer_id_hash, valid_from));
    CREATE TABLE products (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), external_product_id text NOT NULL, title text, vendor text, product_type text, category text, status text, UNIQUE (merchant_id, external_product_id));
    CREATE TABLE variants (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), product_id uuid NOT NULL REFERENCES products(id), external_variant_id text NOT NULL, sku text, UNIQUE (merchant_id, external_variant_id));
    CREATE TABLE orders (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), customer_id uuid REFERENCES customers(id), external_order_id text NOT NULL, ordered_at timestamptz NOT NULL, currency char(3) NOT NULL, gross_item_sales numeric NOT NULL, line_discounts numeric NOT NULL, shipping_revenue numeric NOT NULL, tax numeric NOT NULL, net_sales numeric NOT NULL, financial_status text, fulfillment_status text, source text NOT NULL, raw_source_record_id uuid REFERENCES raw_source_records(id), UNIQUE (merchant_id, external_order_id));
    CREATE TABLE order_lines (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), order_id uuid NOT NULL REFERENCES orders(id), product_id uuid REFERENCES products(id), variant_id uuid REFERENCES variants(id), quantity integer NOT NULL CHECK (quantity > 0), gross_unit_price numeric NOT NULL, line_discount numeric NOT NULL, net_line_sales numeric NOT NULL, cogs_per_unit_nullable numeric, raw_source_record_id uuid REFERENCES raw_source_records(id));
    CREATE TABLE refunds (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), order_id uuid NOT NULL REFERENCES orders(id), external_refund_id text NOT NULL, refunded_at timestamptz NOT NULL, refund_amount numeric NOT NULL, raw_source_record_id uuid REFERENCES raw_source_records(id), UNIQUE (merchant_id, external_refund_id));
    CREATE TABLE return_lines (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), order_line_id uuid NOT NULL REFERENCES order_lines(id), returned_at timestamptz NOT NULL, quantity integer NOT NULL CHECK (quantity > 0), refund_amount numeric NOT NULL, restocked boolean NOT NULL DEFAULT false);
    CREATE TABLE behavior_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), customer_id uuid REFERENCES customers(id), session_id text, event_type text NOT NULL, occurred_at timestamptz NOT NULL, observed_at timestamptz NOT NULL, product_id uuid REFERENCES products(id), variant_id uuid REFERENCES variants(id), page_path text, properties_jsonb jsonb NOT NULL DEFAULT '{}', provider text NOT NULL, external_event_id text NOT NULL, raw_source_record_id uuid REFERENCES raw_source_records(id), UNIQUE (merchant_id, provider, external_event_id));
    CREATE TABLE campaigns (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), provider text NOT NULL, external_campaign_id text NOT NULL, name text, channel text, created_at_source timestamptz, sent_at_nullable timestamptz, UNIQUE (merchant_id, provider, external_campaign_id));
    CREATE TABLE campaign_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), customer_id uuid NOT NULL REFERENCES customers(id), campaign_id uuid NOT NULL REFERENCES campaigns(id), event_type text NOT NULL, occurred_at timestamptz NOT NULL, properties_jsonb jsonb NOT NULL DEFAULT '{}');
    CREATE TABLE cost_records (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), cost_type text NOT NULL, entity_type text NOT NULL, entity_id text NOT NULL, valid_from timestamptz NOT NULL, valid_to timestamptz, amount numeric NOT NULL, currency char(3) NOT NULL, source text NOT NULL, provenance_json jsonb NOT NULL DEFAULT '{}');
    CREATE TABLE data_health_runs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), as_of timestamptz NOT NULL, status text NOT NULL, prediction_ready boolean NOT NULL, experiment_ready boolean NOT NULL, economics_ready boolean NOT NULL, summary_json jsonb NOT NULL);
    CREATE TABLE data_health_checks (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), data_health_run_id uuid NOT NULL REFERENCES data_health_runs(id), check_name text NOT NULL, capability text NOT NULL, status text NOT NULL, observed_value text, expected_value text, tolerance numeric, detail_json jsonb NOT NULL DEFAULT '{}');
    CREATE TABLE customer_state_snapshots (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), customer_id uuid NOT NULL REFERENCES customers(id), as_of timestamptz NOT NULL, state_version text NOT NULL, feature_schema_hash text NOT NULL, observed_state_json jsonb NOT NULL, predictive_state_json jsonb NOT NULL, support_json jsonb NOT NULL, uncertainty_json jsonb NOT NULL, data_health_run_id uuid REFERENCES data_health_runs(id), state_hash text NOT NULL, UNIQUE (merchant_id, customer_id, as_of, state_version));
    CREATE TABLE population_state_snapshots (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), as_of timestamptz NOT NULL, population_size bigint NOT NULL, state_json jsonb NOT NULL, uncertainty_json jsonb NOT NULL, state_hash text NOT NULL, UNIQUE (merchant_id, as_of, state_hash));
    CREATE TABLE model_training_runs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), decision_type text NOT NULL, target_definition text NOT NULL, train_start timestamptz NOT NULL, train_end timestamptz NOT NULL, model_candidates_json jsonb NOT NULL, winner_json jsonb, calibration_json jsonb NOT NULL, temporal_validation_json jsonb NOT NULL, status text NOT NULL);
    CREATE TABLE opportunities (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), discovered_at timestamptz NOT NULL, opportunity_type text NOT NULL, title text NOT NULL, description text NOT NULL, population_definition_json jsonb NOT NULL, observed_problem_json jsonb NOT NULL, predicted_risk_json jsonb NOT NULL, addressable_value_json jsonb NOT NULL, evidence_level text NOT NULL, support_status text NOT NULL, confidence_status text NOT NULL, status text NOT NULL);
    CREATE TABLE opportunity_evidence (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), opportunity_id uuid NOT NULL REFERENCES opportunities(id), evidence_type text NOT NULL, metric_name text NOT NULL, estimate numeric, lower_bound numeric, upper_bound numeric, source_snapshot_id uuid, model_version text, provenance_json jsonb NOT NULL);
    CREATE TABLE action_candidates (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), opportunity_id uuid NOT NULL REFERENCES opportunities(id), action_type text NOT NULL, parameters_json jsonb NOT NULL, evidence_level text NOT NULL, expected_outcome_json jsonb NOT NULL, expected_economics_json jsonb NOT NULL, support_json jsonb NOT NULL, uncertainty_json jsonb NOT NULL, recommendation text NOT NULL);
    CREATE TABLE experiments (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), opportunity_id uuid REFERENCES opportunities(id), name text NOT NULL, status text NOT NULL, eligibility_definition_json jsonb NOT NULL, primary_outcome text NOT NULL, secondary_outcomes_json jsonb NOT NULL, economic_outcome_definition_json jsonb NOT NULL, outcome_window_days integer NOT NULL CHECK (outcome_window_days > 0), randomization_unit text NOT NULL, randomization_seed text NOT NULL, stratification_json jsonb NOT NULL, sample_size_plan_json jsonb NOT NULL, power_plan_json jsonb NOT NULL, analysis_plan_json jsonb NOT NULL, frozen_at timestamptz, experiment_spec_hash text UNIQUE);
    CREATE TABLE experiment_arms (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), experiment_id uuid NOT NULL REFERENCES experiments(id), arm_name text NOT NULL, action_type text NOT NULL, action_parameters_json jsonb NOT NULL, allocation_probability numeric NOT NULL CHECK (allocation_probability > 0 AND allocation_probability <= 1), is_control boolean NOT NULL DEFAULT false);
    CREATE TABLE experiment_assignments (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), experiment_id uuid NOT NULL REFERENCES experiments(id), customer_id uuid NOT NULL REFERENCES customers(id), arm_id uuid NOT NULL REFERENCES experiment_arms(id), assigned_at timestamptz NOT NULL, assignment_probability numeric NOT NULL CHECK (assignment_probability > 0 AND assignment_probability <= 1), stratum text, assignment_hash text NOT NULL, UNIQUE (experiment_id, customer_id));
    CREATE TABLE experiment_exposures (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), experiment_id uuid NOT NULL REFERENCES experiments(id), customer_id uuid NOT NULL REFERENCES customers(id), arm_id uuid NOT NULL REFERENCES experiment_arms(id), exposed_at timestamptz NOT NULL, provider text NOT NULL, exposure_reference text);
    CREATE TABLE experiment_outcomes (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), experiment_id uuid NOT NULL REFERENCES experiments(id), customer_id uuid NOT NULL REFERENCES customers(id), window_start timestamptz NOT NULL, window_end timestamptz NOT NULL, purchase boolean NOT NULL, order_count integer NOT NULL, gross_sales numeric NOT NULL, net_sales numeric NOT NULL, refunds numeric NOT NULL, returns numeric NOT NULL, cogs numeric, shipping_subsidy numeric, campaign_variable_cost numeric, payment_cost numeric, contribution_profit numeric, outcome_version text NOT NULL, UNIQUE (experiment_id, customer_id, outcome_version));
    CREATE TABLE experiment_results (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), experiment_id uuid NOT NULL REFERENCES experiments(id), analyzed_at timestamptz NOT NULL, estimator text NOT NULL, effect_json jsonb NOT NULL, uncertainty_json jsonb NOT NULL, economic_effect_json jsonb NOT NULL, support_json jsonb NOT NULL, validity_checks_json jsonb NOT NULL, result_hash text NOT NULL UNIQUE);
    CREATE TABLE merchant_learning_records (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), experiment_id uuid NOT NULL REFERENCES experiments(id), pre_action_state_definition_json jsonb NOT NULL, action_definition_json jsonb NOT NULL, outcome_definition_json jsonb NOT NULL, estimated_effect_json jsonb NOT NULL, uncertainty_json jsonb NOT NULL, support_region_json jsonb NOT NULL, economics_json jsonb NOT NULL, evidence_level text NOT NULL, recorded_at timestamptz NOT NULL);
    CREATE TABLE jobs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), job_type text NOT NULL, status text NOT NULL, payload jsonb NOT NULL, attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL, locked_at timestamptz, completed_at timestamptz, error text);
    CREATE TABLE audit_log (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), merchant_id uuid NOT NULL REFERENCES merchants(id), event_type text NOT NULL, actor_reference text NOT NULL, occurred_at timestamptz NOT NULL, detail_json jsonb NOT NULL);
    """)
    op.execute(
        "CREATE INDEX behavior_events_merchant_customer_time ON behavior_events (merchant_id, customer_id, occurred_at); CREATE INDEX behavior_events_merchant_type_time ON behavior_events (merchant_id, event_type, occurred_at); CREATE INDEX orders_merchant_customer_time ON orders (merchant_id, customer_id, ordered_at); CREATE INDEX jobs_claim ON jobs (status, available_at) WHERE status = 'PENDING';"
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Table owners otherwise bypass RLS. FORCE keeps Render's runtime/owner role subject to it.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = tenant_predicate(table)
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
