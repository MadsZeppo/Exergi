# V7.2 Economic Policy Engine Model Card

## Intended use

Offline development and evaluation of randomized multi-arm commerce actions with pre-treatment
features, known propensities and monetary outcomes. It is not an autonomous campaign executor.

## Implemented architecture

- One-stage per-arm Ridge, forests, gradient boosting and robust regression.
- Two-part purchase-times-positive-value hurdle model.
- X learner, randomized R learner and known-propensity DR learner.
- DR pseudo-outcome causal forest and shallow policy tree.
- Strict OOF nuisances, held-out DR/IPW/Hájek evaluation, governance masks and BAU fallback.
- Observable-only sequential pause/revalidation controller with committed-risk accounting.

## Current evidence boundary

Buy Baits uses only pre-treatment device, known assignment probability `1/8`, and the package's
short-term retailer-profit field. Development shows no material personalized uplift and substantial
static-policy instability. The correct current behavior is not to promote a personalized model.

Level 4 contribution-profit authority is prohibited because COGS and variable costs are not
separately observable. Validation, sealed test and official model selection are not opened/frozen.
