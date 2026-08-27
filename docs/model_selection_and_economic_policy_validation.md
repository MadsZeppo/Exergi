# Development-only model selection and economic policy validation

## Scope

This pass changes model selection and policy validation only. It adds no World State,
product surface, integration, or new commercial domain.

Commercial Twin no longer assumes that its DR learner is the default. Defaults are now
resolved by decision type from a frozen development-only tournament. Final-test metrics
cannot enter the selector.

## Implementation

The new typed selector compares candidate development policy value subject to an explicit
calibration tolerance. It records the winner, policy, eligible and rejected candidates,
freeze time, and the invariant `test_metrics_used_for_selection=false`.

The registry now stores empirical defaults by decision type. This prevents a winner for
binary ad targeting from silently becoming the default for continuous discount decisions.

The customer presentation is fail-closed. An internal `ACT` is rendered as `TEST THIS`
unless the evidence payload explicitly contains a validated
`customer_facing_do_this_enabled=true`. `TEST THIS` and `NOT ENOUGH EVIDENCE` remain
available internally.

## Benchmark 1: Criteo randomized uplift

Decision type: `binary_ad_targeting`.

Candidates: static, outcome propensity, S-learner, T-learner, X-learner, DRLearner, and
the former Commercial Twin DR alias. The development policy was evaluated at a frozen
20% capacity. Models outside the development calibration tolerance were rejected before
policy-value ranking.

Development selected **S-learner**, not DR:

| Metric | Result |
|---|---:|
| Development policy value | 0.00299638 |
| Development calibration error | 0.00011589 |
| Final AUUC | 0.00330211 |
| Final Qini | 0.00054563 |
| Final calibration error | 0.00008214 |
| Final top-20% policy value | 0.00303335 |

The customer gate failed. On final test its gated value was 0.00297796, below ungated
S-learner (0.00306574), simple targeting (0.00302760), and treat-all (0.00307444).
Consequently customer-facing `DO THIS` is disabled.

## Benchmark 2: Hillstrom randomized economic benchmark

This is a second real randomized commerce benchmark using Men's email versus control and
observed customer spend. It contains 42,613 rows split 60/20/20 into train, development,
and untouched test.

The economic scenario is explicit:

- treatment cost: $0.50 per contacted customer;
- maximum capacity: 20%;
- policy value: RCT/IPW expected spend minus contact cost;
- candidate capacities: 5%, 10%, and 20%.

The $0.50 cost is a benchmark scenario assumption, not a Hillstrom data field. Predictions
for development and test were frozen in the Prediction Ledger before final outcomes were
evaluated.

Candidates were static, outcome propensity, S-learner, T-learner, X-learner, and a
cross-fitted DR learner. Development selected **outcome propensity at 20% capacity**:

| Metric | Result |
|---|---:|
| Development net policy value | $0.93438/customer |
| Development calibration error | $0.76971 |
| Final selected net value | $0.68098/customer |
| Treat-all net value | $0.56305/customer |
| Treat-none net value | $0.68791/customer |
| Random 20% capacity value | $0.66294/customer |
| Test-best feasible challenger | outcome propensity at 10% |
| Test-best feasible value | $0.81835/customer |
| Selected-policy regret | $0.13737/customer |
| Final calibration error | $1.18250 |
| Final Qini | -0.03466 |

The development winner beat random 20% allocation slightly on test, but did not beat
treat-none and was identical to the defined simple targeting comparator. Thus selective
targeting did **not** establish real incremental economic value. The test-best 10% policy
is reported only as an oracle benchmark for regret; it is not promoted or used to retune
selection.

The economic gate also failed on both the required development and final comparisons.
Customer-facing `DO THIS` remains disabled; internal guidance is limited to `TEST THIS`
or `NOT ENOUGH EVIDENCE`.

## Verdict

| Capability | Verdict | Reason |
|---|---|---|
| Development-only model selection | PASS | Winner freezes before final outcome evaluation |
| Decision-specific defaults | PASS | Registry resolves separate defaults by decision type |
| DR no longer assumed best | PASS | S-learner won Criteo; outcome ranking won Hillstrom development |
| Customer-facing gate safety | PASS | Fail-closed and empirically disabled on both benchmarks |
| Criteo selective uplift ranking | MIXED | S-learner performs well, but gating adds no value |
| Cost-constrained economic policy | FAIL | Frozen winner does not beat treat-none/simple targeting on untouched test |
| Overall success criterion | FAIL | A robust economically superior selective policy has not been demonstrated |

The failure is substantive: high-variance spend makes the single Hillstrom development
selection unstable, calibration degrades on test, and the frozen 20% policy loses to no
treatment. More development evidence or a predeclared repeated-development validation
scheme may be warranted, but changing the selector after seeing this test result would be
test tuning and was not done.

## Files

Created:

- `src/decision_engine/decision/model_selection.py`
- `scripts/select_criteo_decision_model.py`
- `src/decision_engine/benchmark/hillstrom_economic.py`
- `scripts/run_hillstrom_economic_benchmark.py`
- `tests/test_model_selection.py`
- `tests/test_hillstrom_economic.py`
- this report

Changed:

- `src/decision_engine/registry/store.py`
- `src/commercial_twin/presentation.py`
- `tests/test_experiment_registry_dashboard.py`
- `tests/test_commercial_presentation.py`

Primary artifacts:

- `artifacts/benchmarks/criteo/definitive-seed-42-v2/development_model_selection.json`
- `artifacts/benchmarks/criteo/definitive-seed-42-v2/selected_model_product_view.json`
- `artifacts/benchmarks/hillstrom/economic-capacity-seed-42/summary.json`
- frozen prediction Parquet files, development/final policy tables, calibration table,
  Prediction Ledger, and model registry under the same Hillstrom artifact directory.
