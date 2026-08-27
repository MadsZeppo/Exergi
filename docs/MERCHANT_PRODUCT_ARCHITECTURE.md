# Merchant Product Architecture V1

Merchant Validation V1 implements the production-shaped loop:

`source → immutable raw version → canonical records → Data Trust → point-in-time state → opportunity → action evidence → frozen experiment → randomized outcome → economics → ledger → learning record`.

PostgreSQL is the product system of record. Partitioned Parquet plus DuckDB/Polars remain the heavy analytical compute layer. The existing DuckDB Prediction Ledger is preserved; merchant services expose the learning history without pretending DuckDB is a multi-tenant application database.

Every product record is scoped by `organization_id` and/or `merchant_id`. PostgreSQL RLS-compatible policies use `app.merchant_id`. Service methods also reject cross-merchant access.

The deterministic in-memory demo service exists only for integration tests and UI demonstration. It is not a production database and is always labelled `SYNTHETIC DEMO — NOT COMMERCIAL EVIDENCE`.

## Run

```bash
cp .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn commercial_twin.merchant_validation.api:app --reload --port 8000
npm run dev
```
