# Exergi V7 forensic audit

**Authority:** pre-implementation audit  
**Date:** 27 August 2026  
**Prior authoritative status:** V6.2 development FAIL; no V6.2 freeze or official reveal  
**Immutable inputs:** all V1–V6.2 reports, manifests, reveal markers, code and artifacts

## Scope inspected

The audit covered:

- `PROJECT_STATUS.md`;
- `ALT_BYGGET_VERIFIED_CUSTOMER_TWIN_OG_DECISION_LAYER.md`;
- `docs/HELE_PRODUKTET_VERIFIED_CUSTOMER_TWIN.md`;
- V6, V6.1 and V6.2 final/development/assurance reports;
- V6–V6.2 worlds, simulators, discovery, safety, risk, inference, evaluators, runners and freeze guards;
- causal estimators, OPE, CUPED/CUPAC, experiment design, VOI and economics;
- `MerchantLearningRecord`, learning matcher and merchant experiment service;
- Hillstrom, Criteo, Open Bandit, X5 and Dunnhumby adapters/runners;
- existing test coverage and persisted development/final markers.

This audit was written before any V7 implementation.

## A. DGP/policy co-adaptation

### A1. Shared latent variable between opportunity score and treatment effect — verified defect

In `benchmarks/ecommerce_decision_layer_v6/world.py`, a latent `severity` vector generates both:

- `observed.opportunity_signals`; and
- the magnitude of `truth.global_effects`.

V6.2 inherits the same merchant builder through `build_scenario_merchant`. The policy therefore
receives a noisy transform of the same latent quantity used to generate economic treatment value.
This is not direct oracle-array leakage, but it is DGP/policy co-adaptation and can make discovery
substantially easier than a genuinely independent DGP family.

### A2. Source priors are generated directly from oracle effects — verified defect

`build_source_records` in the V6 simulator constructs each cross-merchant source effect as:

```text
truth.global_effects[family, action] + Gaussian noise
```

It does not simulate source assignments, outcomes, maturity, attrition or an estimator. V6.2 calls
the same helper. The target policy therefore receives oracle-derived source summaries presented as
historical experimental evidence. This can inflate hierarchical cold-start and transport results.

Required V7 correction: source evidence must be produced through the same randomized, cost-aware,
outcome-maturity path as target evidence. Oracle effects may only label the frozen result afterward.

### A3. Regime-to-base-world mapping — plausible co-adaptation

V6.2 maps named safety scenarios to a small set of V6 base regimes. Those base regimes determine
effect scale and observed opportunity-signal scale. The policy does not receive the scenario enum,
but repeated development across A–G creates substantial implicit familiarity with the same effect
families and mappings.

### A4. Pack reuse and threshold exposure — verified limitation

Pack A was repeatedly used for development. B/C/D exposed a zero-exploration failure and were then
consumed. A TEST fallback was added before E/F/G, which were also consumed. They are development
diagnostics, not holdouts. V7 must not call any A–G result validation or final evidence.

### A5. Merchant IDs and seeds — no policy leakage found

Merchant IDs encode seeds and runners recover the seed from the ID to generate common randomness.
The policy ranking and lifecycle do not branch on merchant ID, seed or scenario name. This is an
engineering smell but not observed policy leakage. V7 should pass RNG state explicitly and use
opaque IDs.

### A6. Hidden change point and future outcomes — no direct policy input found

V6.2 freezes candidate selection and assignment before calling the truth-dependent outcome block.
`truth.change_episode`, oracle family values and potential effects are used in outcome generation
or evaluator labels. They are not passed into discovery, safety or risk functions before the
decision. Indistinguishable-world tests found zero decision differences at identical histories.

## B. Evaluation unit and inference

### B1. Merchant-level primary inference — verified good mechanism

V6–V6.2 aggregate episodes within merchant and bootstrap paired merchant-level differences. They
do not use customer rows or weekly episodes as independent primary replicates. Common random
numbers are used symmetrically by running policies with the same target merchant and seed.

### B2. DGP clustering is incomplete — plausible defect

The bootstrap resamples merchants, but each scenario usually has only two or three merchants and
the analysis does not perform a second clustering level by DGP family. Results can therefore be
dominated by a few effect families even when merchant-level confidence intervals are positive.

### B3. Tail estimates are underpowered — verified limitation

Pack-A p95/p99/max pathwise drawdown is estimated from only 64 merchant paths. E/F/G have similar
fleet scale. A p99 quantile at this sample size is effectively an interpolation near the single
largest path and does not have a reported uncertainty interval. Torture-grid cells are systematic
counterfactual variants, not independent merchant paths, and cannot substitute for independent
tail replication.

### B4. Multiplicity is not fully controlled — verified defect

`alpha_for_regime` allocates alpha across regime restarts for one action sequence. Each action and
family owns a separate sequence using the same base alpha. Promotion, suspension, reactivation,
multiple actions, multiple families, many worlds and repeated version attempts therefore do not
share one declared family-wise error budget.

### B5. Evaluator changes after reveal — verified historical defect, transparently reported

The V6 raw false-ACT evaluator used a global-effect intercept and misclassified heterogeneous and
post-drift ACTs. A post-reveal reporting-only audit corrected the interpretation without rerunning
official decisions. The original result remains immutable, but V6 safety claims must rely on the
audited lower bound, not the frozen raw field.

## C. False-ACT semantics

V7 must report all of the following separately:

1. **Raw harmful exposure:** assigned non-control units with negative incremental potential
   contribution profit.
2. **Raw harmful episode:** an ACT episode whose population/declared-segment policy value is
   non-positive.
3. **Pre-observable harm:** harm incurred before a relevant post-change outcome could mature.
4. **Avoidable/post-observable harm:** new exposure after a policy-visible informative harmsignal
   and the allowed operational stop latency.
5. **Policy-level harm:** negative average incremental value for the deployed population or
   segment.
6. **Individually negative responder:** a customer with negative individual potential outcome
   under a population policy that may still have positive policy value.

### C1. Individual responders and policy correctness — verified good interpretation

V6.2 reports harmful individual exposure separately from false ACT. An individual negative
responder does not automatically make a positive population policy wrong.

### C2. Avoidable-harm label depends on observed sign — verified semantic defect

The V6.2 evaluator labels a matured post-change batch informative only when its realized contrast
is negative. A policy-visible matured batch exists even when noise leaves its point estimate
positive; whether it is a legitimate harmsignal must be specified using a frozen statistical rule,
not oracle timing plus realized sign. V7 must report maturity availability and legitimate signal
availability separately.

### C3. Exposure- and decision-weighted reporting — partial

V6.2 reports episode false-ACT rates and customer harmful-exposure rates. Confidence intervals are
provided for episode proportions but not for exposure-weighted harm. V7 needs merchant-clustered
uncertainty for both.

## D. Sequential validity

### D1. Outcome maturity — verified mostly correct

Randomized batches enter action evidence only through `mature_pending` after `matures_at`.
Selection and assignment are frozen before truth-dependent outcomes are generated.

### D2. Risk reservation can expire before actual outcome maturity — verified defect

Risk commitment maturity is calculated from static `config.feedback_clocks[family]`. The actual
randomized batch maturity uses truth-dependent `outcome_delay`, which reaches four episodes in
development scenarios while default clocks are one or two episodes. Risk can therefore be released
before the corresponding causal/economic batch matures.

### D3. TEST exposure is not reserved — verified defect

`exposure_decision` is invoked only in `LIMITED_ACTIVE` or `ACTIVE`. TEST, WATCH and REVALIDATING
randomized treatment assignments create real downside but do not reserve the committed global risk
ledger. This violates the stated interpretation of total open assigned risk.

### D4. No action-family sub-budget — verified defect

V6.2 keeps one merchant-level `RiskState`, but it has no separate family-level commitment budget.
Concurrent family exposure cannot be audited against family limits.

### D5. Risk reservation is too narrow — verified defect

Credible downside is `max(minimum floor, -adaptive lower bound)`. It does not take the maximum of:

- posterior downside;
- empirical action-family downside floor;
- merchant-declared worst case;
- distribution-shift stress downside.

### D6. Propensity logging after forced arm repair — plausible defect

When an assignment has fewer than two observations in an arm, V6.2 manually rewrites assignments
but still logs the original Bernoulli propensity. This is rare at current sample sizes but means the
recorded probability is not the exact probability under the repaired assignment algorithm.

### D7. Attrition, noncompliance and interference — non-defect limitation

The current V6.2 simulator does not model a full assignment/delivery/exposure/noncompliance chain,
outcome censoring or household spillover. Its sequential validity result cannot be transported to
those settings.

### D8. Permanent sentinel — partial

V6.1/V6.2 retain randomized monitoring while ACTIVE. The existence and minimum allocation of a
permanent control across every lifecycle transition is not represented as an immutable protocol
contract.

## E. Economic semantics

### E1. Merchant experiment contribution-profit equation — verified mechanism

The merchant validation service computes:

```text
gross item sales
- line discounts
- refunds
+ shipping revenue
- COGS
- merchant shipping cost
- campaign variable cost
- payment processing cost
```

It fails closed when required cost components are missing.

### E2. Gross-versus-net discount semantics — plausible defect

The contract names `gross_item_sales` and subtracts `line_discounts`, which is correct only if gross
sales are truly pre-discount. Other parts of the repository use `net_sales`. There is no immutable
semantic contract preventing a connector from supplying net sales and then subtracting discount a
second time.

### E3. Costs on all assigned customers — partial

The synthetic merchant service charges campaign cost per assigned row and shipping/discount cost
through outcomes. The generic scientific `contribution_profit` helper is much narrower. A unified
contract must require costs for non-converters as well as converters and tie every delayed return
or refund to the original assignment.

### E4. Missing maturity keys — verified defect

`ExperimentOutcome` has no assignment timestamp, eligibility snapshot, delivery/exposure field,
household interference key or outcome maturity timestamp. Returns and refunds cannot be proven to
belong to the correct assignment window from this contract alone.

### E5. Synthetic CP remains assumption-dependent — non-defect limitation

V6–V6.2 contribution profit is generated by the benchmark DGP. It supports synthetic economic
mechanism claims only. It is not real merchant profit.

## Dataset evidence audit

### Hillstrom

- 64,000 randomized customer rows are present.
- SHA-256: `27bab8c5d3669f26ec08ebb50a0a78317542f29501156f2e2af6781fab4cd7e2`.
- Outcomes are visit, conversion and spend.
- Cost fields are absent; profit is scenario analysis only.
- Existing results identify a best static email arm but not personalization value.

### Criteo Uplift V2

- 13,979,592 rows and 12 anonymized features are present.
- Repository expected SHA-256:
  `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc`.
- `treatment` is assignment/ITT.
- `exposure` is post-assignment and is correctly excluded from features by the adapter.
- Outcomes are proxy visit/conversion; no revenue or profit claim is possible.

### Open Bandit

- The local data is the publisher's 10,000-row-per-policy quick sample, not the 26M full dataset.
- It contains logged action probabilities and click rewards.
- The V5 audit reconstructed a BTS target distribution because exact context-specific target
  propensities were unavailable for the comparison; its result is PARTIAL.
- Click is engagement, not profit.

### X5 RetailHero

- Local files match the publisher-distribution MD5 values used by the adapter.
- `treatment_flg` documents performed communication, but the accessible provenance does not prove
  random assignment.
- Allowed authority: ranking/feature robustness under `UNKNOWN_ASSIGNMENT`.
- Causal and profit PASS are forbidden.

### BAUR profit-uplift

- The paper is openly available, but no lawful public row-level BAUR dataset or publisher download
  was located.
- No scraping or inferred reconstruction is permitted.
- V7 may add an adapter/acquisition contract and cite the authors, but the dataset is unavailable.

## VERIFIED DEFECTS

1. Opportunity signals and treatment effects share latent `severity` in the V6 DGP.
2. Cross-merchant source priors are generated directly from oracle effect arrays.
3. Alpha is allocated per action/regime sequence, not globally across actions and families.
4. V6.2 risk reservation can release before actual batch maturity.
5. TEST/WATCH/REVALIDATING downside is absent from committed risk.
6. There is no separate action-family committed-risk budget.
7. Reserved downside omits empirical, merchant-declared and shift-stress floors.
8. V6's original false-ACT evaluator was incorrect; official safety requires the audit.
9. Outcome contracts lack maturity, noncompliance and interference linkage.
10. V6.2 A–G are all consumed development packs.

## PLAUSIBLE DEFECTS

1. Scenario/base-regime reuse allows implicit DGP familiarity.
2. Merchant-only bootstrap may understate DGP-family uncertainty.
3. Tail quantiles are too weakly replicated for precise p99 claims.
4. Forced assignment repair is not reflected in exact logged propensity.
5. Gross-versus-net sales semantics can double-count discounts if a connector maps fields wrongly.
6. Existing discovery scores conflate opportunity magnitude, action viability and test priority.

## NON-DEFECT LIMITATIONS

1. Pre-observable harm cannot be eliminated when profitable and harmful worlds have identical
   observable histories before delayed outcomes mature.
2. Individual negative responders do not invalidate a positive supported population policy.
3. BAU/AVOID on null or harmful worlds is a correct outcome.
4. A homogeneous positive world should select the best static policy, not manufacture CATE.
5. Public proxy-outcome RCTs do not provide real contribution-profit evidence.
6. Unknown X5 assignment provenance requires downgraded claims even if ranking is stable.

## REQUIRED FIXES

1. Separate opportunity discovery, action viability, experiment prioritization, segment policy,
   heterogeneity and risk deployment into typed components.
2. Generate new V7 DGP families independently of policy scores and source summaries.
3. Build source evidence through randomized outcomes, not truth arrays.
4. Introduce global and family committed-risk reservations for every non-BAU assigned batch.
5. Release reservations only on the recorded batch maturity or conservative expiry.
6. Allocate sequential alpha across actions, families and restarts.
7. Gate personalization against the best supported static policy with honest held-out value.
8. Introduce immutable dataset evidence and claim-authority registry.
9. Add complete real-merchant economics, assignment, maturity and interference contracts.
10. Create new disjoint H/I/J development, K/L/M validation and sealed N final packs.

## CLAIMS THAT MUST BE WITHDRAWN OR DOWNGRADED

- “V6 hierarchical transfer proves general cross-merchant learning” must be downgraded because
  source summaries were generated from oracle effects rather than source experiments.
- “V6.2 risk budget covers all open downside” is false; TEST and delayed-clock mismatch are omitted.
- “V6.2 p99 is established” is too strong at the available number of independent paths.
- “X5 is randomized causal evidence” is not supported by accessible provenance.
- “Open Bandit validates commercial value” is forbidden; the reward is click.
- “Hillstrom validates contribution profit” is forbidden without actual cost fields.
- “Full State improves policy value” is unsupported; V6 FULL and RFM-only were identical.
- “Real merchant profit is documented” remains forbidden.

## Audit decision

The proposed V7 architecture is justified. The largest issues cannot be repaired by another V6.2
threshold grid. V7 must isolate value identification from personalization, make all assigned risk
committed and maturity-aware, and build independent DGP/source-evidence paths.

Implementation may proceed, but V7 final reveal remains prohibited until new development and
validation gates pass without retuning.
