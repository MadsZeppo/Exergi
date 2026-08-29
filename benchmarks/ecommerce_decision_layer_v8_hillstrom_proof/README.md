# Exergi V8 — Hillstrom proof

This isolated package performs one preregistered, one-shot validation of the static Mens Email action
selected on Hillstrom DEVELOPMENT. It never uses SEALED_TEST and does not modify V7.2 or V7.3.

Before reveal:

```bash
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.development_reconstruction
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.freeze
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.validation_runner --dry-run
```

The authorized reveal requires the committed freeze hash:

```bash
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.validation_runner \
  --reveal --freeze-commit <committed-freeze-hash>
```

After the reveal, reports can be regenerated only from the immutable aggregate JSON result. The raw
validation parser is not invoked during report regeneration.
