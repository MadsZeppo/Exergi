# Merchant Validation V1 — Build Report

**Build date:** 26 August 2026  
**Evidence label:** `SYNTHETIC DEMO — NOT COMMERCIAL EVIDENCE`  
**Customer Twin scientific thesis:** unchanged: **NO**

## Capability status

| Layer | Status | Exact result |
|---|---|---|
| Database | PARTIAL | One PostgreSQL/Alembic migration, 34 tables, indexes and RLS-compatible policies. Offline PostgreSQL SQL generation passed. Docker/PostgreSQL runtime is unavailable locally, so the migration was not applied to a live server. |
| Shopify | PARTIAL | Pinned `2026-07` contract, resources, credential boundary and HMAC webhook verification. Live GraphQL pagination/backfill was not run and full HTTP implementation remains. |
| Klaviyo | PARTIAL | Pinned revision contract, resources and `CAUSAL_ASSIGNMENT_NOT_IDENTIFIED` boundary. Live pagination/backfill was not run and full HTTP implementation remains. |
| Web events | PARTIAL | Typed single/batch FastAPI ingestion, tenant auth, idempotency and timestamp/schema validation. PostgreSQL repository persistence and production rate limiting remain. |
| CSV import | PARTIAL | Validated canonical parser for costs, experiments, returns, offline orders and behavior. Templates and database normalization jobs remain. |
| Data Trust | PARTIAL | Orders, duplicates, identity resolution, temporal validity, COGS and randomized-assignment checks with independent readiness. Full source reconciliation and quarantine persistence remain. |
| Customer Twin | PARTIAL | Point-in-time observed state, deterministic hashes, no PII, no future events and predictive fields withheld before merchant backtest. |
| Merchant backtest | PARTIAL | Authority and readiness contracts preserved; no new executable merchant rolling-origin tournament was completed. Predictions remain `NOT_VALIDATED`. |
| Opportunity Engine | PARTIAL | Executable repeat-rate/high-intent detector with sample floor, uncertainty, persistence and `OBSERVED GAP` distinction. Remaining detector registry entries are documented but not executable. |
| Action Engine | PARTIAL | Generic no-action, free-shipping and discount candidates; all return `TEST_THIS` without action-specific randomized evidence. |
| Experiment Engine | PARTIAL | Frozen multi-arm spec, HMAC assignment, exact probabilities, sample-size formulas and randomized ITT analysis. CUPED, AIPW, balance diagnostics, Holm correction and exposure API remain. |
| Economics | PARTIAL | Contribution-profit contract and missing-cost refusal implemented. Merchant-specific return/accounting policy persistence remains. |
| Ledger learning loop | PARTIAL | Pre-outcome record, appended result and `MerchantLearningRecord` work in the demo service. Durable PostgreSQL repository plus bridge to the existing DuckDB ledger remain. |
| API | PARTIAL | OpenAPI/FastAPI surface for health, connectors, events, customer base/twin, opportunities, experiment create/freeze/assign/analyze/results and ledger. Sync, exposures, action-generation and job endpoints remain. |
| Frontend | PARTIAL | Eleven compiled Next.js routes cover onboarding, data health, customer base, opportunities, detail, experiment setup/results, ledger and connections. They currently render the deterministic demo rather than a live API session. |
| End-to-end demo | PASS | 180 twins, one opportunity, `TEST_THIS`, 180 immutable assignments, contribution-profit ITT, two ledger records and one learning record. Synthetic only. |
| Real merchant evidence | NONE | No credentials or real merchant were connected. |

## PostgreSQL

Migration count: **1**.

Core table count: **34**. The schema covers organizations, merchants, connections, immutable source versions, canonical commerce, events/campaigns, costs, Data Trust, snapshots, opportunities/actions, experiments, outcomes/results, jobs, audit logs and merchant learning.

`DATABASE_URL` configures Alembic. SQLite is not a product fallback. Offline generation with PostgreSQL dialect passed. Live migration status is **NOT EXECUTED** because Docker and a local PostgreSQL server are unavailable in this environment.

## Customer state

Observed fields include tenure, last activity/purchase, purchase/order count, historical value, AOV, category/product affinity, browsing/cart recency, cart frequency, recent intent, cadence, promotion exposure, refund rate, lifecycle and history support. Predictive quantities are empty until merchant-specific chronological validation passes.

## Capability matrix produced by demo

- observed customer state: `READY`;
- purchase prediction: `NOT_VALIDATED`;
- opportunity discovery: `READY`;
- historical causal response: demo assignment metadata available, but no new-action winner inferred;
- experiment design: `READY`;
- incremental profit: `READY` for the complete synthetic fixture;
- `DO THIS`: disabled for discount, shipping and retention actions;
- `TEST THIS`: enabled.

## Randomization, power and estimation

Assignment uses deterministic HMAC-SHA256 over:

```text
merchant_id | experiment_id | customer_id
```

with a frozen secret seed and cumulative arm probabilities. Assignment is reproducible, one customer appears once and each row stores its exact probability.

Binary two-proportion and continuous mean-difference sample-size calculations are implemented. Primary analysis is randomized difference in means under ITT with standard error and 95% CI. CUPED and AIPW are **NOT IMPLEMENTED** in the merchant product service and are not claimed complete.

## Economics

```text
Contribution Profit = Gross Item Sales
                    - Line Discounts
                    - Refunds
                    + Shipping Revenue
                    - COGS
                    - Merchant Shipping Cost
                    - Variable Campaign Cost
                    - Payment Processing Cost
```

If a required variable cost is missing, the function returns no contribution profit. Revenue is not relabelled profit.

## API routes implemented

- `GET /api/v1/merchants/{id}/data-health`
- `POST /api/v1/connections/shopify`
- `POST /api/v1/connections/klaviyo`
- `POST /api/v1/events`
- `POST /api/v1/events/batch`
- `GET /api/v1/customer-base`
- `GET /api/v1/customers/{id}/twin`
- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/{id}`
- `POST /api/v1/experiments`
- `POST /api/v1/experiments/{id}/freeze`
- `POST /api/v1/experiments/{id}/assign`
- `GET /api/v1/experiments/{id}`
- `POST /api/v1/experiments/{id}/analyze`
- `GET /api/v1/experiments/{id}/results`
- `GET /api/v1/ledger`

## Frontend routes compiled

- `/onboarding`
- `/data-health`
- `/customer-base`
- `/opportunities`
- `/opportunities/[id]`
- `/experiments`
- `/experiments/new`
- `/experiments/[id]/results`
- `/ledger`
- `/settings/connections`
- existing `/`

All merchant pages label the current data as synthetic demo evidence.

## Executed verification

| Check | Result |
|---|---|
| End-to-end demo | PASS — artifact generated |
| Merchant Validation tests | PASS — 12 |
| Full `pytest -q` | PASS — 230 tests |
| `ruff check .` | PASS |
| `mypy src` | PASS — 129 source files |
| `npm run build` | PASS — 11 routes |
| Alembic PostgreSQL offline SQL | PASS |
| Live PostgreSQL migration | NOT EXECUTED — Docker/PostgreSQL unavailable |

Demo artifact: `artifacts/merchant_validation_v1/demo_result.json`.

## Commands

Full local stack when Docker is installed:

```bash
cp .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn commercial_twin.merchant_validation.api:app --reload --port 8000
npm run dev
```

Synthetic acceptance flow:

```bash
uv run python scripts/run_end_to_end_demo.py
```

## What needs real credentials

- Shopify Admin API backfill, incremental sync and real webhooks;
- Klaviyo profile/event/campaign/message history;
- any explicitly enabled write/activation connector.

No credential was fabricated and no live connection is reported.

## What needs the first real merchant

- source-total reconciliation;
- merchant-specific rolling-origin prediction tournament;
- prospective prediction calibration;
- real opportunity review;
- a frozen randomized action experiment;
- outcome/assignment integrity validation;
- incremental contribution profit from actual costs;
- prediction-versus-randomized-reality history;
- enough repeated experiments for action-response learning.

## Final status

```text
PRODUCT SOFTWARE:
    PARTIAL

FIRST MERCHANT READY:
    NO

REAL CUSTOMER TWIN EVIDENCE:
    NOT YET — REQUIRES PROSPECTIVE MERCHANT VALIDATION
```
