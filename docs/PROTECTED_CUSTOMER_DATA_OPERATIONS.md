# Exergi protected customer data operations

Status: founder-prepared operational contract, pending qualified legal review.

This runbook covers the two controls previously answered **No** in Shopify's protected
customer data review: merchant privacy/data-protection agreements and enforced retention.
It does not claim a certification. Legal entity, notice address, governing law and transfer
terms must be checked by qualified counsel before public commercial contracting.

## Official requirements used

- [Shopify protected customer data requirements](https://shopify.dev/docs/apps/launch/protected-customer-data)
  require merchant-facing data practices, privacy/data-protection agreements and enforced
  retention periods.
- [Shopify privacy law compliance](https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance)
  requires `customers/data_request`, `customers/redact` and `shop/redact`, valid HMAC handling,
  a 2xx response and completion within 30 days. Shopify sends `shop/redact` 48 hours after
  uninstall.
- [Shopify webhook subscriptions](https://shopify.dev/docs/apps/build/webhooks/subscribe)
  requires the compliance subscription configuration to be deployed as an app version.
- [Vercel cron management](https://vercel.com/docs/cron-jobs/manage-cron-jobs) sends the
  production `CRON_SECRET` as a Bearer token. A Hobby cron can run once daily, with approximate
  invocation time.

## Enforced contract

| Category | Enforced cutoff | Action |
|---|---:|---|
| OAuth nonces | 24 hours | Deleted daily |
| Webhook receipt metadata | 30 days | Deleted daily |
| Reconciled raw protected payloads | 90 days | Canonical references detached, payload deleted |
| Privacy export artifacts | 30 days | Deleted daily |
| Customer redaction | Immediate webhook transaction | Raw records removed; analytical linkage and customer rows removed |
| `shop/redact` | Raw/token removal immediately; full shop hard-delete after 7 days | Daily worker |
| Uninstall | Raw/token removal immediately; full shop hard-delete after 30 days unless reconnected | Daily worker |
| Agreement/security evidence | Up to 7 years after termination | Data-minimized legal/audit evidence only |

The global maintenance path does not receive a privileged database role. It can enumerate only
the data-minimized `maintenance_tenants.merchant_id` registry when the transaction-local
maintenance mode is set. Every actual read and deletion then runs in a separate ordinary tenant
transaction under PostgreSQL `FORCE ROW LEVEL SECURITY`. No `SECURITY DEFINER` function or
dynamic SQL is used.

## Agreement evidence

Before `/api/v1/shopify/connect` can create an OAuth nonce, the current Terms, Privacy Policy and
DPA must be actively accepted. The browser submits only the current version and `accepted=true`.
The authenticated backend derives organization and merchant from the verified Clerk token.

One acceptance row records:

- exact agreement version and hashes of Terms, Privacy, DPA and Subprocessors;
- organization and merchant IDs resolved server-side;
- a keyed hash of the Clerk subject;
- database acceptance time;
- keyed hashes of request IP and truncated user-agent metadata;
- only the exact approved dashboard origin, otherwise `direct`.

The unique merchant/version/subject key makes replay idempotent. A document change requires a
new version and new acceptance.

## Secrets and deployment

Never paste these values into chat, screenshots, Git, `render.yaml` values or client-side code.

1. Generate an independent value locally with `openssl rand -base64 48`.
2. In **Render → exergi-api → Environment**, set `RETENTION_CRON_SECRET` to that value.
3. In **Vercel → Exergi → Settings → Environment Variables**, set production `CRON_SECRET` to
   the same value.
4. Let Render generate and retain `AGREEMENT_AUDIT_KEY`, or enter a separate 32+ byte value
   directly in Render. Never reuse the cron secret.
5. Deploy the Render service first. Its start command runs `alembic upgrade head` before Uvicorn.
6. Verify `https://<render-domain>/healthz` is healthy.
7. Deploy the Vercel production dashboard. `vercel.json` invokes `/api/cron/retention` daily at
   03:17 UTC. Vercel authenticates the proxy; the proxy authenticates Render using the same
   dedicated value. Neither endpoint returns or logs the secret.
8. Invoke one manual authenticated maintenance request from the provider console and verify a
   `COMPLETED` run in **Settings → Compliance**. Do not put the secret in a browser URL.

## Shopify webhook deployment and evidence

1. Confirm the production client ID and URLs in `shopify.app.toml` through the linked Shopify app
   configuration; do not commit a client secret.
2. Deploy a new Shopify app version with `shopify app deploy` and approve only the existing
   read-only scopes.
3. In the Partner Dashboard version details, verify all four routes point to
   `/api/v1/shopify/webhooks`:
   `customers/data_request`, `customers/redact`, `shop/redact`, `app/uninstalled`.
4. Trigger test deliveries from Shopify's supported tooling. Confirm 2xx, a receipt row, replay
   deduplication and then privacy-job completion in the compliance dashboard.
5. Only after this live check, set `SHOPIFY_WEBHOOKS_VERIFIED_AT` in Render to the UTC timestamp
   of the evidence. This variable changes the dashboard from `DECLARED_NOT_VERIFIED` to
   `LIVE_VERIFIED`; it does not bypass a test.

## When the two Shopify answers can honestly become Yes

**Privacy and data-protection agreements with merchants = Yes** only when all of these are true:

- the public versioned pages are deployed;
- legal identity/contact blanks have been completed and the founder-pending-review warning is
  accurate;
- the connecting merchant actively accepted that exact version;
- the acceptance row and hashes can be shown in the data-minimized compliance dashboard.

**Enforced retention periods = Yes** only when all of these are true:

- migration `0005_compliance_retention` is applied;
- both provider secrets are configured;
- at least one daily production run is recorded as `COMPLETED`;
- cutoff, customer-redaction, shop-delete and cross-tenant RLS checks pass;
- all four Shopify webhook subscriptions are deployed and live-verified.

Code merged but not deployed is not sufficient evidence for either Yes.
