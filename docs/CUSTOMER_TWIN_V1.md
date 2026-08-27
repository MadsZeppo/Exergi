# Merchant Customer Twin V1

`MerchantCustomerTwin` contains an observed state and optional validated predictive quantities.

Observed state includes tenure, activity/purchase recency, purchase and order counts, historical net value, AOV, category/product affinity, browsing/cart recency, cart frequency, recent intent, purchase cadence, promotion exposure, refund behavior, lifecycle and history support.

State is point-in-time, deterministic and hashed. No raw name, email or phone is used. Post-treatment campaign opens/clicks cannot leak into the baseline state for that campaign.

Predictive fields remain empty until merchant-specific chronological backtests pass frozen readiness gates. A public-data model is not assumed to transfer. The correct unsupported output is `NOT_VALIDATED_FOR_THIS_MERCHANT`.
