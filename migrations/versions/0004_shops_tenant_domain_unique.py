"""Match the shops upsert target with a named tenant/domain unique constraint."""

from __future__ import annotations

from alembic import op

revision = "0004_shops_tenant_domain_unique"
down_revision = "0003_clerk_identity_tenants"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_shops_merchant_shop_domain"


def upgrade() -> None:
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "shops",
        ["merchant_id", "shop_domain"],
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "shops", type_="unique")
