# V7.3 Independent Synthetic Economic DGP

## Isolation

The DGP is independent of Hillstrom and Buy Baits. It does not copy their outcomes, customers,
sample means, fold values, or treatment effects. Gate-development uses seed root `7303001` and 500
independent worlds for each of ten families, totaling 5,000 worlds. Gate-validation and sealed seed
roots were preregistered but never opened because development selected no gate.

Deployable `GateInput` contains observed matured monetary outcomes, randomized assignment,
pretreatment features, hashed split keys, logged propensity, maturity, declared cost, budget, support,
and assignment-integrity diagnostics. Finite-population potential outcomes and true net value live in
a separate evaluator-only `WorldTruth`; gate functions have no truth/oracle parameter.

## Families

The fixed families are null, globally harmful, materially positive, weak positive, qualitative
heterogeneity, sparse responders, outlier-driven response, negative contribution margins, common
shock/effect reversal, and integrity/support failure. Sample sizes are 600, 1,200, or 2,400.
Baseline purchase probability ranges from 0.5% to 5%. Positive amounts use lognormal, Pareto, or
compound/Tweedie-like distributions. Supported assignment probabilities range from 35% to 65%.

The integrity family cycles through immature outcomes, corrupted propensity, insufficient overlap,
unsupported action, assignment contamination, and missing/delayed outcomes. Common gate
prerequisites must abstain in these worlds. Treatment costs and per-unit budgets are observed gate
inputs; negative-margin worlds distinguish revenue-like response from actual economic value.

## Scientific boundary

Synthetic truth evaluates decisions only after they are frozen for a world. It never enters policy
features, support logic, thresholds, confidence, or gate selection. Synthetic value is mechanism
evidence, not real merchant profit evidence.
