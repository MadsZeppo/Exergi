# Reproduction

This package is regenerated only from tracked persisted artifacts. It does not reopen V8/V9 raw
data, rerun either validation, or access any sealed outcome.

```bash
.venv/bin/python -m benchmarks.three_dataset_monetary_proof.audit
.venv/bin/python -m benchmarks.three_dataset_monetary_proof.report
.venv/bin/pytest -q tests/test_three_dataset_monetary_proof.py
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
git diff --check
```

Immutable authorities:

- V8 freeze/dry-run ancestry: `6bf1f92ee7ac5d6afb1b7859cf09582266da6ce2`;
- V8 one-shot result commit: `0fa7944`;
- V9 preregistration: `4638172`;
- V9 freeze: `1fd6c27`;
- V9 one-shot result commit: `e4fefa9`;
- V14 remains `753eb567d79d52a0401705647350bb3ded983834`;
- third-dataset qualification checkpoint: `f718547`.

Determinism is checked by generating the report set twice into separate temporary directories and
comparing every byte.
