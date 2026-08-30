"""Database URL compatibility for SQLAlchemy's explicit psycopg 3 driver."""

from __future__ import annotations


def normalize_sqlalchemy_url(database_url: str) -> str:
    """Select psycopg 3 for driverless PostgreSQL URLs without changing other URLs."""
    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    if database_url.startswith("postgresql://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgresql://')}"
    return database_url
