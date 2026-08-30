from __future__ import annotations

from unittest.mock import patch

import pytest

from commercial_twin.database_url import normalize_sqlalchemy_url
from commercial_twin.shopify.repository import SqlShopifyRepository


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "postgres://user:password@internal-host:5432/exergi",
            "postgresql+psycopg://user:password@internal-host:5432/exergi",
        ),
        (
            "postgresql://user:password@internal-host:5432/exergi?sslmode=require",
            "postgresql+psycopg://user:password@internal-host:5432/exergi?sslmode=require",
        ),
        (
            "postgresql+psycopg://user:password@internal-host:5432/exergi",
            "postgresql+psycopg://user:password@internal-host:5432/exergi",
        ),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
    ],
)
def test_normalize_sqlalchemy_url(source: str, expected: str) -> None:
    assert normalize_sqlalchemy_url(source) == expected


def test_shopify_repository_normalizes_render_database_url() -> None:
    with patch("commercial_twin.shopify.repository.create_engine") as create_engine:
        SqlShopifyRepository.from_url("postgresql://user:password@internal-host/exergi")

    create_engine.assert_called_once_with(
        "postgresql+psycopg://user:password@internal-host/exergi",
        pool_pre_ping=True,
    )
