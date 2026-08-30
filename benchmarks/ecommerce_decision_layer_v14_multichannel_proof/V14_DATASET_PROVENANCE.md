# Exergi V14 dataset provenance

Status: `V14_REALITY_CALIBRATION_QUALIFIED`

## Qualified independent backbones

### 84.51° Complete Journey

- Authority: CRAN `completejourney`, which identifies 84.51° Complete Journey 2.0 as the origin.
- Canonical URL: <https://cran.r-project.org/package=completejourney>
- Origin URL: <https://www.8451.com/area51>
- Local version: `completejourney` 1.1.0 source snapshot.
- License: CC0.
- Archive SHA-256: `3ab70c37cc1fae797ae4b135b29acada5b56eb7eec32e1631b9fbe7c5abd4b7b`.
- Scope: 1,469,307 grocery transaction lines, 155,848 baskets and 2,469 households over 53
  numbered weeks.

### UCI Online Retail II

- Authority: UCI Machine Learning Repository.
- Canonical URL: <https://archive.ics.uci.edu/dataset/502/online+retail+ii>
- DOI: `10.24432/C5CG6D`.
- License: CC BY 4.0.
- Archive SHA-256: `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb`.
- Scope: 1,067,371 transaction lines from a UK non-store retailer over two years, including
  cancellation indicators.

Both sources were already present in ignored raw storage. V14 verifies their bytes and requires the raw
archives to be read-only. It does not redownload, modify or commit them.

## Permitted use

The sources calibrate empirical marginal distributions only: order value, lines per basket, repeat
frequency, discount share, seasonality and cancellation/return-proxy prevalence. V14 generates new
synthetic merchant, customer, order and product IDs. It never joins people or entities across sources.

The sources contain no randomized multi-action treatment truth for V14. They do not calibrate treatment
effects, potential outcomes, optimal actions or policy value. Those are preregistered semi-synthetic
evaluator constructs and remain unavailable to the engine.
