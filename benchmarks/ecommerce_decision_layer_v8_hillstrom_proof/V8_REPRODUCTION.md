# V8 Reproduction

The validation outcome is permanently consumed. Do not rerun the raw-data analysis.
Regenerate Markdown deterministically from the immutable result JSON with:

```bash
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.report
```

This command reads only `V8_VALIDATION_RESULT.json` and `V8_FREEZE_MANIFEST.json`; it
does not open raw Hillstrom data or any held-out split.
