# V7.2 Preregistration

Frozen before any V7.2 assurance-validation or real-data validation/sealed-test run.

## Evidence and splits

- Highest randomized unit split by SHA-256 into DEVELOPMENT 50%, VALIDATION 25%, SEALED_TEST 25%.
- Split seed root: `72_2001`; only hashed unit IDs may be persisted.
- Known randomized propensities are primary. Estimated propensities are diagnostics only.
- No Dataset B/C split is created before official authority and complete raw data exist.
- Real sealed access requires three qualified datasets, sequential PASS, validation PASS, source and
  dependency freeze, and exact model/threshold hashes.

## Economic objective and candidates

Primary selection score is held-out doubly robust net value versus BAU, then increment versus best
static, lower 95% bound, fold stability, downside, calibration/support and complexity. Predictive
metrics are diagnostic.

Candidates are ridge, random forest, extra trees, histogram gradient boost, Tweedie, Huber and a
logistic × log-Ridge smearing hurdle model, all fit per arm with strict cross-fitting. Baselines are
BAU, every allowed static arm, best static and a simple preregistered segment policy. Action costs are
subtracted per action and prohibited arms are excluded before argmax.

## Sequential gates

- unsupported ACT: 0;
- merchant budget violations: 0;
- immature risk released at pause: 0;
- maximum ordinary post-observable harmful continuation: 0 units;
- maximum feedback-clock stop latency: 0 periods;
- maximum harmful revalidation exposure: 10 units across the two-harm-episode fixture, using
  five-unit reduced batches;
- positive-world mean value retained: at least 55%;
- null-world ACTIVE rate: at most 5%;
- reactivation success in at least 80% of reactivation paths;
- identical observable histories imply identical decisions.

The sequential development seed root is `720001`. Assurance validation must use a disjoint root.

## Stop contract

Missing Buy Baits authority, missing Dataset C, sequential failure or validation failure closes all
real-world sealed tests. No threshold may be altered after a sealed reveal.
