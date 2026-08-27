# Customer Population Engine V3 — frozen hypothesis

## Evidence entering V3

Customer Population Engine V2 showed:

- strong customer ranking, purchase AUC approximately 0.9066;
- poor aggregate incidence calibration;
- materially improved conditional order/value modeling;
- decisive superiority of a last-period top-down forecast for buyer, order and revenue totals.

Cosmetics February 2020 is burned diagnostic data. It cannot select, calibrate or validate V3.

## V3 hypothesis

A hybrid hierarchical forecast can preserve validated customer heterogeneity while using
development-selected top-down information to stabilize aggregate totals.

The architecture under test is:

```text
top-down forecast: how much
+
bottom-up propensity: who
→ monotonic probability reconciliation
→ coherent buyer/order/revenue allocation
→ cohort/category/customer distributions
```

The preferred incidence reconciliation is a logit-intercept adjustment:

```text
p_i* = sigmoid(logit(p_i) + alpha)
sum(p_i*) = forecast existing buyers
```

This preserves ranking exactly. Naive scaling is a required challenger. Orders and revenue
must remain heterogeneous and non-negative while reconciling to their selected aggregate
anchors.

## Falsifiable product claim

V3 is useful only if it approaches or beats top-down aggregate accuracy while retaining
out-of-time customer/cohort/category heterogeneity. Merely forcing totals to a top-down
forecast is not sufficient.

The benchmark must answer whether V3 adds value beyond:

`aggregate forecast + customer propensity ranking`.

If a simple implementation of that combination is equivalent, the full population-simulator
thesis should be simplified accordingly.

## New validation source

Full REES46 Multi-Category development plus final history would require roughly 12 GB of
compressed monthly downloads and substantially more temporary storage. This is not
responsible in the current workspace.

V3 therefore uses the official REES46 electronics purchase-history dataset: approximately
50 MB compressed, 8 chronological months, real pseudonymous customer/product transactions.
It is a new source and final window, distinct from both burned Cosmetics February and burned
electronics-event February.

Exact splits and success criteria are frozen in the V3 artifact directory before the final
month is read.
