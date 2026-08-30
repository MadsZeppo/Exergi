# Shopify vertical-slice architecture audit

Date: 2026-08-30  
Repository baseline: `30c41ac94223fa7d35819069e581f194c53ea1dd`

## Existing product surface

- The repository has one Next.js 16 App Router application in `app/`; it is deployed as a
  Next.js project through `vercel.json`. The marketing page and merchant product pages share
  the same deployment.
- The product API is FastAPI in
  `src/commercial_twin/merchant_validation/api.py`. It currently serves an in-memory demo
  service. Its `X-Merchant-Id` check is not production authentication.
- PostgreSQL is the declared persistence layer. Alembic and SQLAlchemy are installed, and
  migration `0001_merchant_validation_v1` already defines much of the canonical decision,
  experiment and ledger model with merchant-scoped row-level-security policies.
- The scientific engine already supplies useful typed contracts for point-in-time state,
  economic authority, evidence boundaries, experiments, learning records and append-only
  ledgers. Immutable benchmark artifacts are not a runtime dependency and must remain outside
  this integration.
- The current Shopify connector is only a status contract plus webhook-HMAC helper. It does not
  install, store a token, call Shopify, persist raw data or run a sync.

## Reuse decisions

- Extend the existing FastAPI service rather than create a second backend.
- Extend the existing Next.js merchant shell rather than create another frontend.
- Reuse PostgreSQL, Alembic, tenant IDs, audit log, jobs, raw-source, customer, order, product,
  state, opportunity, experiment and ledger concepts.
- Preserve the existing evidence authority: observational Shopify history can support
  decomposition, diagnostics, scenarios and test recommendations, but not causal `DO` claims.
- Use an additive migration. Do not rewrite or regenerate historical migrations or benchmark
  results.

## Missing production mechanisms

1. Real Shopify OAuth, nonce replay protection, expiring offline-token refresh and encrypted
   token persistence.
2. A real authenticated merchant principal. The existing merchant-ID header is retained only
   for the legacy demo API; Shopify endpoints use a signed Exergi session. A production identity
   provider remains an external deployment resource.
3. Shopify GraphQL client, Bulk Operations orchestration, resumable sync state, raw versioned
   payload storage and canonical idempotent upserts.
4. Privacy webhooks, uninstall/disconnect, deletion workflow and webhook replay protection.
5. Canonical Shopify economics, point-in-time state, descriptive analyses and honest decision
   cards backed by persisted data.
6. Real dashboard loading/empty/error/not-ready states. Existing merchant pages currently show
   hard-coded synthetic values.

## Locked Shopify contract

- GraphQL Admin API and webhook payload version: `2026-07` (latest stable on the audit date).
- Default scopes: `read_orders`, `read_products`, `read_inventory`, `read_customers`,
  `read_returns`. There are no write scopes.
- `read_all_orders` is disabled unless both Exergi configuration and Shopify approval enable it.
  Without it, the UI states that Shopify normally exposes only the latest 60 days.
- Shopify Payments balance/fee access is an optional, separately approved scope and never a
  prerequisite for net-revenue reporting.
- Direct identifiers (name, email, phone, addresses) are not queried. Shopify customer IDs are
  converted to merchant-scoped HMAC pseudonyms before the analytical schema is populated.
- Public-app token exchange requests expiring offline tokens and stores both access and refresh
  credentials encrypted. Token refresh is serialized per shop and replaces the pair atomically.

## Deployment resources still required

- Shopify Partner/Dev Dashboard app and development store.
- `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, approved redirect URL and app base URL.
- A 32-byte token-encryption key, a distinct OAuth-state key, a distinct customer-pseudonym key,
  and an Exergi session-signing key from a production secret manager.
- Managed PostgreSQL with TLS and migrations applied.
- A production identity provider that issues the Exergi merchant session. A dev-only session
  bootstrap is allowed only when explicitly enabled and cannot run in production mode.
- HTTPS endpoints and a worker/scheduler for bulk-sync polling and token refresh.
- Protected-customer-data selection/review, `read_all_orders` approval if desired, and optional
  Shopify Payments permission.

## Implementation sequence

1. Add security/config contracts and additive PostgreSQL schema.
2. Implement OAuth, encrypted installation records, refresh, disconnect and compliance webhooks.
3. Implement read-only GraphQL/Bulk Operations, immutable raw ingestion and canonical mapping.
4. Implement economic completeness, point-in-time state, observational analyses, reconciliation
   and decision cards.
5. Connect the existing merchant dashboard to a typed API with non-fabricated states.
6. Add focused security/reconciliation tests, full QA and first-merchant runbook.

No Shopify credential was available during this audit, so no installation, permission grant or
live-data result is claimed.
