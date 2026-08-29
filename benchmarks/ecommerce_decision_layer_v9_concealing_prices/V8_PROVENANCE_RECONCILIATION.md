# V8 Provenance Reconciliation

## Purpose

This record clarifies three distinct V8 Git references without reopening Hillstrom VALIDATION,
recomputing any V8 estimate, changing any V8 result artifact, or removing the permanent consumed
lock.

## Exact commit roles

| Role | Commit | Parent | Meaning |
|---|---|---|---|
| Freeze-artifact creation | `7d0df4d8b6d7d15c855adbbd315048b590fe9ec5` | `0a089ff1b1a73ba4cf6a1fd96c44a879f53aec3b` | First committed tree containing V8 preregistration, frozen analysis config, claim contract, estimator/runner source, pre-reveal QA, DEVELOPMENT reconstruction and `V8_FREEZE_MANIFEST.json`. |
| Last committed pre-reveal tree | `6bf1f92ee7ac5d6afb1b7859cf09582266da6ce2` | `7d0df4d8b6d7d15c855adbbd315048b590fe9ec5` | Added only the successful outcome-isolation dry-run record. This was the exact committed tree authorized for the one-shot reveal. |
| Result persistence | `0fa794497dcea419a9322b70e5f69291a41d3c2c` | `6bf1f92ee7ac5d6afb1b7859cf09582266da6ce2` | Persisted the reveal-start record, permanent consumed lock, sufficient statistics, immutable validation result, reports, claim card, proof dashboard and post-reveal QA. |

Git ancestry is linear and verified:

```text
0a089ff1 → 7d0df4d8 → 6bf1f92e → 0fa79449
             freeze      reveal-ready   result
```

## Label clarification

`7d0df4d…` is correctly called the **freeze-artifact commit**. `6bf1f92e…` is correctly called the
**last pre-reveal authorization commit**. `0fa79449…` is correctly called the **result commit**.

The freeze manifest was generated while HEAD was its parent `0a089ff1…`; consequently its
`repository_pre_freeze_head` field records that base checkpoint. The commit that first contains the
freeze artifact must necessarily be created after the file exists and is therefore `7d0df4d…`.
This is a normal non-self-referential Git provenance distinction, not a result-integrity defect.

The reveal was authorized against the later clean pre-reveal tree `6bf1f92e…`, whose only delta from
the freeze-artifact commit was the committed dry-run record. Frozen source and configuration hashes
remained those recorded in the freeze manifest.

## Integrity statement

- No Hillstrom outcome was read for this reconciliation.
- Hillstrom VALIDATION was not reopened or recomputed.
- Hillstrom SEALED_TEST was not opened.
- No V8 estimate, confidence interval, p-value, result JSON, hash, freeze source, or consumed lock was
  changed.
- Buy Baits was not accessed or changed.

V8 remains an immutable historical result at commit
`0fa794497dcea419a9322b70e5f69291a41d3c2c`.
