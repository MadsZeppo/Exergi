# Customer Population V1 failure audit

## Status

February 2021 is burned diagnostic data. It must never again be described as untouched or
used to select/tune V2.

## Event semantics

The official REES46 description states that a session may contain multiple purchase events
and that this is one order. The data confirms this:

- 37,346 purchase events;
- 24,344 unique purchase sessions;
- 6,976 sessions contain more than one purchase event;
- median purchase events per purchase session: 1;
- p90 purchase events per purchase session: 3;
- maximum: 44.

Therefore a purchase event is best interpreted as a purchased item/line, not an order.

## Frozen definitions

### Buyer

A pseudonymous `customer_id` with at least one purchase event inside the horizon.

### Order

A unique `(customer_id, user_session)` containing at least one purchase event. V1 grouped
within customer and counted unique sessions, so it did not incorrectly turn every item into
an order. The composite key is explicit in V2 because two session strings are shared across
customers in the full file.

### Item

One purchase event after exact-row deduplication. Quantity is unavailable; it must not be
invented.

### Revenue

Sum of `price` across deduplicated purchase events. It is gross observed item revenue; tax,
shipping, refunds, returns, currency conversion and cost are unavailable.

## Sessions and duplicates

- No purchase row has null customer, session, product, category or price.
- The complete event file contains 655 exact duplicate rows.
- Three exact duplicate rows are purchase events.
- V1 did not explicitly remove exact duplicates.

This is a small but real labeling bug. V2 must deduplicate exact source rows before label
construction and record the number removed.

## Major V1 population-labeling omission

February contains:

- 7,643 purchase-item events;
- 4,945 purchase orders/sessions;
- 4,341 buyers;
- $1,376,815.54 observed item revenue.

Of the February buyers, **3,956 were not present before the 1 February cutoff**. V1's
`build_future_outcomes` left-joined outcomes onto cutoff CustomerState rows. This was valid
for evaluating the existing-customer subpopulation, but the headline “actual population”
silently excluded new customers.

For existing customers only, V1 evaluated:

- 385 buyers;
- 456 orders;
- $155,142.73 revenue.

Thus V1 omitted the new-customer arrival process from total-population generation. V2 must
report and simulate existing and new populations separately, then reconcile them.

## Generative incoherence

V1 independently simulated:

- buyer Bernoulli draws;
- unconditional Poisson order counts;
- independent Gamma customer-spend draws.

Its mean outputs were approximately 363 buyers, 264 orders and $470,101 revenue. Fewer
orders than buyers is impossible under the stated definition. Revenue was not constructed
as the sum of order values conditional on incidence and order count.

This is the main modeling bug. V2 must use a hurdle chain:

```text
purchase incidence
→ conditional order count (minimum one)
→ conditional values for each simulated order
→ summed customer and population revenue
```

## Heavy-tail audit

Observed purchase-item price quantiles in the full V1 source:

| Quantile | Price |
|---|---:|
| p50 | $64.48 |
| p90 | $397.48 |
| p95 | $479.51 |
| p99 | $656.63 |
| max | $3,717.65 |

The observed tail is material but insufficient to explain V1 by itself. V1's spend model
predicted total existing-customer revenue 203% above actual while underpredicting orders.
Therefore the implied predicted order value, not excessive predicted order frequency, caused
the revenue explosion.

The exact multiplicative decomposition confirms this:

| Component | Predicted | Actual | Relative error | Revenue-error contribution |
|---|---:|---:|---:|---:|
| Buyers | 361.4 | 385 | -6.1% | -$30,706 |
| Orders per buyer | 0.730 | 1.184 | -38.4% | -$311,630 |
| Revenue per order | $1,781.52 | $340.23 | +423.6% | +$657,231 |

The three contributions reconcile to the $314,896 existing-customer revenue overprediction.
Customers with zero historical purchases received $456,219 of predicted revenue against
$92,320 actual. The predicted next-4% spender segment was overpredicted by 6,244%, showing
that V1 assigned implausible value to sparse customers outside the very top rank.

The full cohort, lifecycle, history-length, purchase-history, tail, category, and
new-versus-existing tables are persisted in `failure_decomposition.json`.

## Was there a labeling bug?

**Yes, two.**

1. Exact duplicate rows were not explicitly removed, although only three affected purchases.
2. The headline population outcome omitted future new customers without sufficiently clear
   labeling.

The order definition itself was substantially correct. The dominant failure was generative
model incoherence plus missing new-customer arrivals, not the use of session as order.
