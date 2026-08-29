# V7.3 Stability-Assurance Stop Report

## Final decision

No tested gate simultaneously achieved the preregistered safety limits and a materially lower
false-negative rate than the V7.2 fold veto. Therefore:

- no candidate gate was selected;
- no freeze artifact was written;
- gate-validation was not opened;
- synthetic sealed gate-test was not opened;
- Buy Baits was not reassessed;
- Hillstrom was not reassessed;
- Hillstrom VALIDATION and SEALED_TEST were not read;
- all V6/V7/V7.1/V7.2 immutable artifacts remain unchanged;
- BAU remains the safe fallback.

## Core finding

The existing veto has an unacceptable 90.0% false-negative rate in the preregistered supported
materially-positive simulation population. However, the two challengers that improve it by the
required ten percentage points fail safety: bootstrap probability acts in 1.1% of harmful worlds,
and median-of-means acts in 1.5% of harmful and 7.6% of null worlds. A safer, more powerful gate has
not yet been demonstrated.

## Status

`V7_3_GATE_FAILED_HILLSTROM_NOT_REASSESSED`
