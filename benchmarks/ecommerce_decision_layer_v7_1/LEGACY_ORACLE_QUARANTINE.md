# V7.1 legacy oracle quarantine

## Exact defect

`benchmarks/ecommerce_decision_layer_v6/simulator.py::build_source_records` reads
`truth.global_effects[family, action]` and adds Gaussian noise to create a source-prior estimate.
V6.1 imports the same builder, and V6.2 imports it through its runner. Those records then enter
`_source_prior` in discovery/simulation policy paths.

The defect is not evaluator-only use of truth. It is oracle truth transformed into a value that the
policy consumes as if it were external randomized evidence.

## Authority correction

V6–V6.2 files and artifacts remain unchanged. The separate
`LEGACY_CLAIMS_INVALIDATED.json` withdraws source-transfer, warm-start and aggregate policy claims
that depend on these priors. It does not erase the historical FAIL or rewrite results.

## Mechanical V7.1 boundary

- `EvidenceOrigin.LEGACY_ORACLE_DERIVED_PRIOR` and `EVALUATOR_ONLY_ORACLE` are rejected by the
  V7.1 policy evidence constructor.
- Any `oracle_derived` or `evaluation_only` taint is rejected at runtime.
- Source modules beginning with V6, V6.1 or V6.2 benchmark package names are rejected.
- AST scanning rejects imports or calls to `build_source_records`, `_source_prior` and
  `oracle_family_values` in policy source.
- V7.1 official policy runners must construct `V71PolicyEvidence`; they cannot accept an untyped
  tuple of legacy source records.

Evaluator-only oracle references remain legal only in separate evaluation modules after policy
predictions and decisions are frozen. They cannot share fitted state with the policy.

## Consequence

The V6 evidence is quarantined and downgraded. Once import, source-scan and runtime tests pass, this
legacy defect is not a permanent V7.1 stop condition. Any new oracle leak remains a hard stop.

