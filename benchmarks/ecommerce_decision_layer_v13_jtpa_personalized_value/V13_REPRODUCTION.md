# Exergi V13 reproduction

Status: `V13_DEVELOPMENT_NO_PERSONALIZED_POLICY_EARNED_REVEAL`

## Immutable inputs

- Official source archive SHA-256: `3607617e265ec3eac11436f3f19a25e43e3ecf53ba6de6b98a9dede53cc3a76b`
- `scaledui.dta` SHA-256: `ac0b4c26e41accea8d3906cf3fdce3a079c5fbf93da46144f0dd2db7ed35ef03`
- Split hash: `7c4f1bcafd1488cf4b931c8cba948310e1239aa48b8e70e33d23bb04fe91f22f`
- Qualification commit: `47f46a3594493dd8febc614d011d9bda0564d64c`
- Preregistration commit: `54853cf7db0f2d0fe45f3a421be230ed3f4ce10f`
- DEVELOPMENT ID hash: `1d79e8c68427f3e343663f96286b74ce5980a9833647e305933001dc7a8a6b09`
- VALIDATION ID hash: `6f874dbcd31dc3aaadeb2a6567d8ea7a65dbb888ee5f2ca46b8ccce85f12fdfa`

## Deterministic commands

```bash
python -m benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.tournament
python -m benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.placebo
python -m benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.report
pytest -q tests/test_v13_jtpa_qualification.py tests/test_v13_jtpa_preregistration.py tests/test_v13_jtpa_materialization.py tests/test_v13_jtpa_development.py
```

The tournament and placebo commands are DEVELOPMENT-only. Do not create or run a V13 validation runner:
the frozen promotion gate failed. The report command reads only persisted result and manifest artifacts.
