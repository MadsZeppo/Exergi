# V10 qualification reproduction

The checkpoint is deterministic and outcome-free.

1. Verify repository ancestry for V8 commit
   `0fa794497dcea419a9322b70e5f69291a41d3c2c` and V9 commit
   `e4fefa96c0334971413fa3b73104158585edb5fb`.
2. Verify the pinned official README and arXiv PDF hashes recorded in
   `manifests/V10_SOURCE_MANIFEST.json`.
3. Confirm raw storage is ignored and has no `train.csv` or `test.csv`.
4. Confirm `V10_QUALIFICATION_RESULT.json` records no DEVELOPMENT/TEST access, selection,
   freeze, or reveal.
5. Run:

   ```bash
   .venv/bin/pytest -q tests/test_v10_mtlift_qualification.py
   .venv/bin/ruff check benchmarks/ecommerce_decision_layer_v10_mtlift \
     tests/test_v10_mtlift_qualification.py
   .venv/bin/mypy benchmarks/ecommerce_decision_layer_v10_mtlift
   git diff --check
   ```

The official links may change later. A future access attempt must be a new checkpoint; it must
not silently overwrite this access record or reinterpret this stop as a model result.
