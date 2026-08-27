# Commercial Twin refactor audit

Date: 2026-08-25

This audit was frozen before moving or deleting repository files.

| Existing area | Decision | Rationale / target |
|---|---|---|
| `decision_engine/benchmark` | KEEP | Scientific replay, chronological splits, Hillstrom, and continuous benchmarks remain core validation infrastructure. Commerce-facing naming is added through adapters, not destructive moves. |
| `decision_engine/causal` | KEEP | Generic causal math, continuous DR, treatment density, agreement, and diagnostics are product-independent. |
| `decision_engine/forecasting` | KEEP | Generic forecasting behavior-model foundation. |
| `decision_engine/uncertainty` | KEEP | Generic conformal, quantile, and clustered-bootstrap primitives. |
| `decision_engine/simulation` | KEEP | Generic Monte Carlo infrastructure. |
| `decision_engine/decision` | KEEP; DEPRECATE product-specific entry points later | Claims, evidence, experiment design, optimization, and ACT/EXPERIMENT/ABSTAIN remain generic. `continuous_engine` stays as backward-compatible commerce math until a later migration. |
| `decision_engine/economics` | KEEP | Utility/profit functions remain generic objective primitives; commerce mapping lives in `domains.commerce`. |
| `decision_engine/features` | KEEP | Leakage and temporal feature guards remain generic. |
| `decision_engine/metrics` | KEEP | Scientific metrics remain generic. |
| `decision_engine/ledger` | KEEP; EXTEND | Preserve append-only legacy contract and add generic simulation persistence without breaking callers. |
| `decision_engine/registry` | KEEP; EXTEND | Preserve schema/API and add optional action/support/calibration metadata through a compatible v2 table. |
| `decision_engine/robustness` | KEEP | Drift, placebo, and sensitivity remain scientific core. |
| `decision_engine/datasets` | KEEP | Existing research dataset adapters remain benchmark inputs. New product ingestion is separate. |
| `decision_engine/synthetic` | KEEP | Truth-known worlds remain the scientific torture chamber. They are consumed by a commerce fixture rather than duplicated. |
| `decision_engine/dashboard` | KEEP; DEPRECATE demo-only wording | Existing data helpers remain compatible; the app is minimally renamed to a Commercial Twin Research Cockpit. |
| `decision_engine/schemas.py` | KEEP | Existing public imports remain stable. New generic contracts live in `decision_engine.core`. |
| `apps/research_dashboard.py` | RENAME user-facing title only | No polished UI rebuild. Tabs are minimally extended/relabelled. |
| scripts | KEEP | Existing benchmark and dataset entry points remain useful. |
| tests | KEEP; EXTEND | All scientific tests remain authoritative; Commercial Twin tests are additive. |
| artifacts | KEEP | Frozen evidence remains immutable and comparable across product refactors. |
| root `README.md` | RENAME product narrative / REWRITE | Describe Commercial Twin while retaining scientific limitations and core commands. |

## New boundaries

- `decision_engine.core`: generic State/Action/Outcome/Utility/Constraint/Time/Evidence contracts.
- `commercial_twin`: product-layer schemas, twin lifecycle, readiness, calibration, cohorts, and factory.
- `domains.commerce`: discount-specific action and behavior adapter over existing continuous math.

## Delete decision

No file is approved for deletion in this pass. Nothing inspected is both obsolete and
scientifically valueless. Ambiguous demo/product-specific code is retained or deprecated
rather than removed.

## Move decision

No physical move is required to establish the new boundaries without breaking imports.
The continuous-retail benchmark remains at its stable path and is exposed conceptually
through the commerce domain. A later major-version migration may move it with adapters.
