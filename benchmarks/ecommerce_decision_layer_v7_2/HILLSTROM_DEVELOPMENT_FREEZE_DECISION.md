# Hillstrom DEVELOPMENT Freeze Decision

## Decision

**No static model or policy freeze is created. Hillstrom is INCONCLUSIVE.**

| Required check | Result |
|---|---|
| Positive point estimate versus BAU | PASS |
| Conservative adjusted net lower bound positive | PASS: +$0.226670 |
| At least three valid estimators select Mens | PASS: 7/7 |
| Preregistered fold stability | FAIL: one fold is -$0.138 to -$0.168 net |
| Positive net value at locked $0.05 cost | PASS |
| Leakage, overlap, assignment, balance | PASS |
| Bootstrap implementation | PASS |
| Preregistered winsorization sensitivity | FAIL: 99% cap equals $0 |

The candidate is economically promising, and the aggregate adjusted intervals exclude zero. It
nonetheless fails two predeclared stability checks. The project does not promote a preferred result
by dropping the adverse fold or the zero-inflated tail sensitivity.

No model-freeze artifact exists. The machine-readable decision explicitly records
`freeze_artifact_created=false`, `validation_opened=false`, and
`sealed_test_authority=false`.

## Split authority

SEALED_TEST is quarantined because a prior diagnostic displayed one raw row assigned to that split.
It was not used for modeling or scoring, but it is not fully untouched and cannot be final authority.
The split is unchanged. VALIDATION is still unopened, but the failed development gate does not
authorize its one-time reveal.

## Exact status

`HILLSTROM_INCONCLUSIVE_VALIDATION_REMAINS_CLOSED`

