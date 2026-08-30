# Security and privacy overview

Status: engineering baseline for legal/security review; not a legal guarantee.

## Security controls implemented

- Shopify OAuth uses an exact allowlisted `*.myshopify.com` domain, signed short-lived state,
  stored single-use nonce and constant-time callback HMAC verification.
- Public-app authorization requests expiring offline tokens. Access and rotating refresh tokens
  are encrypted with Fernet using a server-side secret-manager key and are never returned to the
  browser or audit log.
- An Exergi session binds every product request to organization and merchant. Repository lookups
  include merchant ID; PostgreSQL tables have merchant row-level-security policies.
- GraphQL calls are pinned to stable version `2026-07`, use HTTPS and carry tokens only in the
  server-side `X-Shopify-Access-Token` header.
- The scope set is read-only. No endpoint creates Shopify mutations, discounts, campaigns,
  customer contacts or autonomous actions.
- Webhooks verify raw-body HMAC before trusting topic/domain headers and deduplicate Shopify
  webhook IDs before processing.
- Direct customer identifiers are not queried. Shopify customer IDs are converted to distinct,
  merchant-scoped HMAC pseudonyms for analysis.
- Security-sensitive operations append audit events without token or payload contents.

## Privacy and lifecycle

Mandatory `customers/data_request`, `customers/redact` and `shop/redact` webhooks share the
verified endpoint. Data requests enter a durable export job. Customer redaction deletes matching
protected raw objects and detaches requested orders from analytical customer state. Shop
redaction deletes raw protected data, destroys stored token material immediately and queues an
ordered hard-delete job for the remaining tenant records. `app/uninstalled` revokes local token
material and starts a retention review.

Recommended default retention, subject to the signed DPA and merchant/legal requirements:

- OAuth nonce: delete after 24 hours;
- webhook receipt/deduplication metadata: 30 days;
- transient bulk result URLs: never persist past import;
- protected raw commerce payloads: 90 days after successful canonical reconciliation;
- canonical merchant records: active contract plus agreed deletion window;
- security audit records: 12 months, with no raw personal fields.

Backups must be encrypted, access-controlled and covered by the same deletion schedule. Test and
production data and keys must be separate.

## Deployment responsibilities

- Store all secrets in the hosting provider's secret manager; never in Git, frontend variables,
  logs or support tickets.
- Require TLS for PostgreSQL, least-privilege service roles, encrypted backups, dependency and
  container scanning, monitoring and restore tests.
- Configure only the dashboard origin for credentialed CORS.
- Run the token-refresh/sync worker and privacy deletion queue continuously with alerts.
- Complete Shopify protected-customer-data review and maintain a current subprocessor register.
- Conduct threat modeling, penetration testing and legal review before a production merchant.

## Incident response outline

1. Triage, contain affected credentials/tenants and preserve relevant non-PII audit evidence.
2. Revoke/rotate Shopify and Exergi secrets; invalidate sessions and stop ingestion if needed.
3. Determine data categories, tenants, time window and legal notification duties.
4. Notify affected merchants and authorities within contractual/legal deadlines.
5. Eradicate the cause, restore from verified clean systems and monitor recurrence.
6. Publish an internal post-incident review and track corrective controls to closure.

## Legal-review placeholders

Before general availability, counsel must approve: privacy policy, terms of service, controller /
processor roles, DPA and SCCs where applicable, retention/deletion schedule, subprocessor list,
data-subject request process, security schedule and incident-notification language.
