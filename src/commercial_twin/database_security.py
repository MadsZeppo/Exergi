"""Fail-closed checks for the PostgreSQL runtime role and tenant RLS posture."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, text


def set_tenant_context(connection: Connection, merchant_id: UUID) -> None:
    """Set the transaction-local tenant used by PostgreSQL RLS policies."""
    connection.execute(
        text("SELECT set_config('app.merchant_id', :merchant_id, true)"),
        {"merchant_id": str(merchant_id)},
    )


@contextmanager
def tenant_transaction(engine: Engine, merchant_id: UUID) -> Generator[Connection, None, None]:
    """Open a transaction that cannot see or mutate rows outside one merchant."""
    with engine.begin() as connection:
        set_tenant_context(connection, merchant_id)
        yield connection


@contextmanager
def shop_route_transaction(engine: Engine, shop: str) -> Generator[Connection, None, None]:
    """Open the narrow pre-tenant lookup used only after Shopify webhook HMAC verification."""
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.shop_domain', :shop, true)"), {"shop": shop}
        )
        yield connection


def verify_runtime_rls(engine: Engine) -> None:
    """Reject privileged runtime roles and application tables that do not force RLS."""
    with engine.connect() as connection:
        role = (
            connection.execute(
                text("""
                SELECT rolname, rolsuper, rolbypassrls
                FROM pg_roles WHERE rolname = current_user
                """)
            )
            .mappings()
            .one()
        )
        if role["rolsuper"] or role["rolbypassrls"]:
            raise RuntimeError("database runtime role must not be superuser or BYPASSRLS")
        unprotected = (
            connection.execute(
                text("""
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND c.relkind = 'r'
                  AND c.relname <> 'alembic_version'
                  AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
                ORDER BY c.relname
                """)
            )
            .scalars()
            .all()
        )
    if unprotected:
        raise RuntimeError(f"database tables missing forced RLS: {', '.join(unprotected)}")
