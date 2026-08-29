# V9 reproduction

## Immutable chain

1. `b81fb2e` — reconcile V8 provenance without reopening V8 outcomes.
2. `4638172` — acquire/verify official OSF files, qualify studies, create outcome-isolated
   splits, and preregister the V9 procedure.
3. `1fd6c27` — record DEVELOPMENT, complete pre-reveal QA, freeze both policies, and pass the
   outcome-free dry run.
4. The result commit records reveal-start, sufficient statistics, immutable validation results,
   consumed locks, reports, and post-reveal QA.

## Commands

```bash
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.prepare
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.development
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.freeze
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.validation_runner
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.finalize
```

The validation command is intentionally no longer reproducible after consumption: a second run
must fail closed. Reports can be regenerated deterministically from immutable result JSON with
the finalization command; it reads no raw data.

QA commands:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
git diff --check
```
