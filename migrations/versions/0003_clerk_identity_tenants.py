# ruff: noqa: E501
"""Clerk identity-to-tenant binding and RLS-safe first-login provisioning."""

from __future__ import annotations

from alembic import op

revision = "0003_clerk_identity_tenants"
down_revision = "0002_shopify_vertical_slice"
branch_labels = None
depends_on = None

MERCHANT_SETTING = "nullif(current_setting('app.merchant_id', true), '')::uuid"
ORGANIZATION_SETTING = "nullif(current_setting('app.organization_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE identity_tenants (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      provider text NOT NULL CHECK (provider = 'clerk'),
      issuer text NOT NULL,
      subject text NOT NULL,
      organization_id uuid NOT NULL REFERENCES organizations(id),
      merchant_id uuid NOT NULL UNIQUE REFERENCES merchants(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (issuer, subject)
    );
    """)
    op.execute("ALTER TABLE identity_tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity_tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY identity_tenants_tenant_policy ON identity_tenants "
        f"USING (merchant_id = {MERCHANT_SETTING}) "
        f"WITH CHECK (merchant_id = {MERCHANT_SETTING})"
    )
    op.execute("DROP POLICY organizations_tenant_policy ON organizations")
    op.execute(
        "CREATE POLICY organizations_tenant_policy ON organizations USING ("
        f"id = {ORGANIZATION_SETTING} OR EXISTS ("
        "SELECT 1 FROM merchants tenant_merchant "
        "WHERE tenant_merchant.organization_id = organizations.id "
        f"AND tenant_merchant.id = {MERCHANT_SETTING})) WITH CHECK ("
        f"id = {ORGANIZATION_SETTING} OR EXISTS ("
        "SELECT 1 FROM merchants tenant_merchant "
        "WHERE tenant_merchant.organization_id = organizations.id "
        f"AND tenant_merchant.id = {MERCHANT_SETTING}))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity_tenants")
    op.execute("DROP POLICY organizations_tenant_policy ON organizations")
    op.execute(
        "CREATE POLICY organizations_tenant_policy ON organizations USING ("
        "EXISTS (SELECT 1 FROM merchants tenant_merchant "
        "WHERE tenant_merchant.organization_id = organizations.id "
        f"AND tenant_merchant.id = {MERCHANT_SETTING})) WITH CHECK ("
        "EXISTS (SELECT 1 FROM merchants tenant_merchant "
        "WHERE tenant_merchant.organization_id = organizations.id "
        f"AND tenant_merchant.id = {MERCHANT_SETTING}))"
    )
