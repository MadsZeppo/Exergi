# First Merchant Onboarding

## Required setup

- merchant organization, timezone and currency;
- merchant-authorized Shopify read access;
- Klaviyo read access if used;
- historical web events or the generic event endpoint;
- returns/refunds;
- cost CSV including COGS, shipping, payment and campaign variable costs;
- ideally at least 12 months of history.

## Strongly preferred evidence

- prior experiment IDs;
- eligibility and assignment records;
- holdout/control flags;
- exact assignment probabilities;
- assignment and exposure timestamps.

Missing browsing data disables rich behavioral state. Missing randomized assignments disables historical causal claims. Missing costs disables contribution-profit decisions. Missing calibration history keeps predictive fields unavailable. Write connectors remain disabled unless `ENABLE_WRITE_CONNECTORS=true` and the merchant explicitly confirms activation.
