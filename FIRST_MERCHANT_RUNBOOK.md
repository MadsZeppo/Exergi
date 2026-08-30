# First merchant / Shopify development-store runbook

This runbook performs a read-only development-store installation. It does not authorize a real
merchant launch or a causal/profit claim.

## 1. External resources

1. Create/select an Exergi app in Shopify Dev Dashboard and a development store.
2. Select protected customer data level 1. Do **not** request name, address, phone or email fields.
3. Configure the five default read scopes in `shopify.app.toml`.
4. Do not enable `read_all_orders` until Shopify separately approves it. Do not enable Shopify
   Payments scope unless the store supports it and approval exists.
5. Set the application URL, exact OAuth redirect URL and HTTPS webhook endpoint for the deployed
   API. Deploy the app configuration so mandatory privacy webhooks are active.
6. Provision PostgreSQL with TLS and a least-privilege Exergi runtime role.

## 2. Secrets

Copy `.env.example` to a local untracked `.env` or use the deployment secret manager. Set:

- `DATABASE_URL`
- `EXERGI_API_BASE_URL` and `EXERGI_DASHBOARD_URL`
- `EXERGI_SHOP_DOMAIN`
- `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET`
- a Fernet `SHOPIFY_TOKEN_ENCRYPTION_KEY`
- independent random `SHOPIFY_OAUTH_STATE_KEY`, `CUSTOMER_PSEUDONYM_KEY` and
  `EXERGI_SESSION_SIGNING_KEY` (at least 32 bytes each)

Never use a `NEXT_PUBLIC_*` variable for a secret.

## 3. Local start

```bash
uv sync --extra dev
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn commercial_twin.merchant_validation.api:app --reload --port 8000
npm install
npm run dev
```

The current repository has no production identity provider. For a development installation,
issue an `exergi_session` with `SessionSigner` for an existing organization/merchant and set it as
an HttpOnly, SameSite=Lax cookie on `localhost`. Do not enable a dev-session minting endpoint in a
production environment. Production must integrate the selected identity provider with the same
signed principal contract.

## 4. Install and sync

1. Open `/onboarding`, enter the permanent `*.myshopify.com` domain and review scopes.
2. Complete Shopify approval. Callback HMAC, state and nonce must all pass.
3. The callback queues the initial read-only bulk sync automatically.
4. Monitor API/job logs by IDs only; never log token, raw payload or customer identifiers.
5. Confirm connection, API version, granted scopes and sync state in Data & Integrations.
6. If the token is near expiry, the next sync refreshes the rotating access/refresh pair. A 401
   or invalid refresh token requires a new OAuth authorization; do not retry indefinitely.

## 5. Acceptance and reconciliation

- Compare the same period/currency with Shopify Admin for order count, gross sales, discounts,
  refunds and net sales.
- Explain every non-zero difference and confirm guest orders are included but not identified.
- Confirm no write scope and no GraphQL mutation other than Shopify's read-only bulk-query start.
- Trigger duplicate webhooks and verify one processing call.
- Trigger the three Shopify CLI compliance webhook fixtures in a non-production store.
- Confirm missing costs downgrade authority; add a versioned assumption only when the merchant
  explicitly supplies and approves it.
- Rebuild state at a historical cutoff and verify late-observed orders/refunds are excluded.
- Confirm the first decision is descriptive and never `DO`.

## 6. Stop conditions

Stop the onboarding and report `DATA_NOT_READY` if OAuth verification, protected-data approval,
tenant identity, reconciliation, currency, order-history coverage or required economic authority
is unresolved. No development-store data or external installation was available while this code
was built, so the live-install step remains unexecuted until the credentials above are supplied.
