from __future__ import annotations

import re
import runpy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from commercial_twin.database_security import verify_runtime_rls

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_0001 = ROOT / "migrations/versions/0001_merchant_validation_v1.py"
MIGRATION_0002 = ROOT / "migrations/versions/0002_shopify_vertical_slice.py"
MIGRATION_0003 = ROOT / "migrations/versions/0003_clerk_identity_tenants.py"
MIGRATION_0004 = ROOT / "migrations/versions/0004_shops_tenant_domain_unique.py"
MIGRATION_0005 = ROOT / "migrations/versions/0005_compliance_retention.py"
PRODUCT_SERVICE = ROOT / "src/commercial_twin/shopify/product_service.py"


def _migration_namespace(path: Path) -> dict[str, Any]:
    return runpy.run_path(str(path))


def _table_columns(path: Path) -> dict[str, set[str]]:
    source = path.read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}
    for match in re.finditer(r"CREATE TABLE\s+(\w+)\s*\((.*?)\);", source, re.DOTALL):
        table, body = match.groups()
        tables[table] = set(
            re.findall(r"(?:^|,)\s*([a-z][a-z0-9_]*)\s+[a-z]", body, re.MULTILINE)
        )
    return tables


def test_every_v1_policy_target_column_exists_in_its_table() -> None:
    namespace = _migration_namespace(MIGRATION_0001)
    tables = tuple(namespace["TABLES"])
    policy_columns = dict(namespace["POLICY_TARGET_COLUMNS"])
    ddl_columns = _table_columns(MIGRATION_0001)

    assert set(policy_columns) == set(tables)
    assert set(ddl_columns) == set(tables)
    for table, policy_column in policy_columns.items():
        assert policy_column in ddl_columns[table], f"{table}.{policy_column} does not exist"


def test_v1_special_policies_follow_real_tenant_relationships() -> None:
    predicate = _migration_namespace(MIGRATION_0001)["tenant_predicate"]

    assert predicate("merchants").startswith("id = ")
    assert "organizations.id" in predicate("organizations")
    assert "data_health_checks.data_health_run_id" in predicate("data_health_checks")
    assert "experiment_arms.experiment_id" in predicate("experiment_arms")
    assert predicate("orders").startswith("merchant_id = ")


def test_every_v2_direct_policy_has_a_merchant_id_column() -> None:
    tables = tuple(_migration_namespace(MIGRATION_0002)["NEW_TABLES"])
    ddl_columns = _table_columns(MIGRATION_0002)

    assert set(ddl_columns) == set(tables)
    for table in tables:
        assert "merchant_id" in ddl_columns[table], f"{table}.merchant_id does not exist"


def test_clerk_binding_policy_and_provisioning_context_are_tenant_scoped() -> None:
    source = MIGRATION_0003.read_text(encoding="utf-8")
    columns = _table_columns(MIGRATION_0003)["identity_tenants"]

    assert {"issuer", "subject", "organization_id", "merchant_id"}.issubset(columns)
    assert "UNIQUE (issuer, subject)" in source
    assert "merchant_id uuid NOT NULL UNIQUE" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "app.merchant_id" in source
    assert "app.organization_id" in source
    assert "SECURITY DEFINER" not in source


def test_shops_upsert_conflict_target_has_matching_named_constraint() -> None:
    service_source = PRODUCT_SERVICE.read_text(encoding="utf-8")
    migration_source = MIGRATION_0004.read_text(encoding="utf-8")
    conflict = re.search(
        r"INSERT INTO shops\s+.*?ON CONFLICT \(([^)]+)\)",
        service_source,
        re.DOTALL,
    )

    assert conflict is not None
    conflict_columns = tuple(value.strip() for value in conflict.group(1).split(","))
    assert conflict_columns == ("merchant_id", "shop_domain")
    assert 'CONSTRAINT_NAME = "uq_shops_merchant_shop_domain"' in migration_source
    assert '["merchant_id", "shop_domain"]' in migration_source
    assert 'down_revision = "0003_clerk_identity_tenants"' in migration_source
    assert "UNIQUE (shop_domain)" in MIGRATION_0002.read_text(encoding="utf-8")


def test_compliance_tables_force_rls_and_maintenance_is_data_minimized() -> None:
    source = MIGRATION_0005.read_text(encoding="utf-8")
    namespace = _migration_namespace(MIGRATION_0005)
    columns = _table_columns(MIGRATION_0005)

    assert set(namespace["TABLES"]) == set(columns)
    assert all("merchant_id" in columns[table] for table in namespace["TABLES"])
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "app.maintenance_mode" in source
    assert "SECURITY DEFINER" not in source
    assert set(columns["maintenance_tenants"]) == {
        "merchant_id", "registered_at", "updated_at",
    }
    assert "UNIQUE (merchant_id, agreement_version, clerk_subject_hash)" in source


def _runtime_engine(
    *, superuser: bool = False, bypass: bool = False, unsafe: list[str] | None = None
) -> MagicMock:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    role_result = MagicMock()
    role_result.mappings.return_value.one.return_value = {
        "rolname": "exergi_runtime",
        "rolsuper": superuser,
        "rolbypassrls": bypass,
    }
    table_result = MagicMock()
    table_result.scalars.return_value.all.return_value = unsafe or []
    connection.execute.side_effect = [role_result, table_result]
    return engine


def test_runtime_table_owner_is_accepted_only_when_all_tables_force_rls() -> None:
    verify_runtime_rls(_runtime_engine())

    with pytest.raises(RuntimeError, match="missing forced RLS"):
        verify_runtime_rls(_runtime_engine(unsafe=["orders"]))


@pytest.mark.parametrize(("superuser", "bypass"), [(True, False), (False, True)])
def test_runtime_role_cannot_bypass_rls(superuser: bool, bypass: bool) -> None:
    with pytest.raises(RuntimeError, match="must not be superuser or BYPASSRLS"):
        verify_runtime_rls(_runtime_engine(superuser=superuser, bypass=bypass))
