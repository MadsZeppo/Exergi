# Dunnhumby Complete Journey — Data Audit

## Source, scope, and license

The downloaded universe is the archived CRAN package `completejourney` version 1.1.0 plus the full
`transactions.rds` referenced by that package's own download function.

- Package source: `https://cran.r-project.org/src/contrib/Archive/completejourney/completejourney_1.1.0.tar.gz`
- Transaction source: `https://github.com/bradleyboehmke/completejourney/raw/master/data/transactions.rds`
- License: `CC0`, verified directly in the package `DESCRIPTION`
- Package SHA-256: `3ab70c37cc1fae797ae4b135b29acada5b56eb7eec32e1631b9fbe7c5abd4b7b`
- Transaction RDS SHA-256: `1fa0700033f1e5d9bb6b09e2be063d8d68474d346e95c50f2833e09d083e0007`
- Retrieved: 2026-08-25

Scope caveat: this is the **CC0 CRAN 1.1.0 one-year universe with 2,469 households**, not the
original two-year, approximately 2,500-household Dunnhumby Source Files release. CRAN calls its
separate RDS the full transaction table for the package universe. All 1,559 campaign households are
present in that table. Results must not be relabeled as validation on the larger two-year release.

## Actual data profile

| Concept | Rows |
|---|---:|
| Transaction lines | 1,469,307 |
| Households | 2,469 |
| Baskets | 155,848 |
| Products | 92,331 |
| Campaign assignments | 6,589 |
| Campaign households | 1,559 |
| Campaigns | 27 |
| Coupon-product-campaign rows | 116,204 |
| Coupon redemptions | 2,102 |

Transaction time runs from 2017-01-01 11:53:26 through 2018-01-01 04:01:20. Campaign starts run
from 2016-11-14 through 2017-12-28; some campaigns therefore lack either pre-history or a complete
30-day outcome window and are excluded by the preregistered temporal rules, not by their outcomes.

The locked 70th-percentile cutoff is 2017-09-20. Fifteen campaigns are eligible for development and
six for backtest. Campaign 18 was selected solely because it had the largest qualified treated
support: 1,133 treated households. The comparison arm contains 1,336 households.

## File provenance

| File | SHA-256 | Rows |
|---|---|---:|
| `transaction_data.csv.gz` | `f4c396be1f82dc82b675bc1f8372d8386f63c464a98215701e77b47b70f7b4ec` | 1,469,307 |
| `product.csv.gz` | `5e43a2859487ac3319a64fb57686168f83b25884219b4ad4de7d7ffc8d97b751` | 92,331 |
| `campaign_table.csv.gz` | `1e0d5dc3651e934ab845e37065c214d856682f9b2e6431a69464341546bfc24a` | 6,589 |
| `campaign_desc.csv.gz` | `6705a89d4dc474ffd55cd63202046bbb0934d33804355805fca2c87bc9a5eb08` | 27 |
| `coupon.csv.gz` | `13766a8488bd08c52acbede783ba26a7364d6c26ca059e335edab246b8484352` | 116,204 |
| `coupon_redempt.csv.gz` | `0923ba4c24f1ae7454ede85727816fc4ad9107553458596af136f21e5bb63c55` | 2,102 |

Full schemas and mappings are persisted in
`data/processed/dunnhumby/complete-journey/provenance.json`.

## Canonical and temporal semantics

- `HOUSEHOLD_KEY` maps to pseudonymous customer ID.
- `BASKET_ID` maps to order ID.
- Product/quantity/sales map to Order/OrderLine.
- `RETAIL_DISC` and `COUPON_DISC` remain observed discount fields.
- Campaign table plus description define observed assignment/exposure windows.
- Coupon redemption is engagement and must not substitute for assignment.
- Campaign assignment is observational, not randomized.
- The primary outcome is any purchase in `[campaign_start, campaign_start + 30 days)`.
- Every state feature ends strictly before campaign start.
- CRAN timestamps are observed. Compatibility `DAY` fields are derived with 2017-01-01 as day 1
  and explicitly recorded as derived.
- Revenue is not profit; no COGS or campaign-cost field is available.

## Identification diagnostics

Corrected post-reveal diagnostic for campaign 18:

- propensity min/median/max: 0.00000017 / 0.3962 / approximately 1.0;
- fraction clipped: 11.87%;
- fraction within `[0.05, 0.95]`: 79.91%;
- treated ESS: 714.7;
- control ESS: 166.3;
- maximum absolute SMD before weighting: 1.399;
- maximum absolute SMD after weighting: 0.360;
- A/A p-value: 0.441;
- A/A SRM p-value: 0.572.

The overlap gate requires at least 80%, and both arms require ESS >= 200. Control ESS and overlap
fail. Residual weighted imbalance is also material. The evidence status is therefore
`INSUFFICIENT`, regardless of the point estimate.

## Freeze/reveal incident

The first final run incorrectly trained the treatment-density nuisance on pooled development
campaign assignments rather than cross-fitting assignment for the selected target campaign. Its
summary is retained as `invalid_first_backtest_summary.json`. Campaign 18 outcomes were revealed,
so the corrected implementation is diagnostic only and the final is burned. It cannot be called an
untouched backtest PASS.
