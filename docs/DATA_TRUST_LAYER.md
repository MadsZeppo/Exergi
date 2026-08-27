# Data Trust Layer V1

Data Trust emits independent capability checks rather than one composite score.

Implemented checks cover source presence/reconciliation hooks, duplicate event IDs, customer identity resolution, temporal validity, COGS coverage and documented randomized assignments. The schema supports separate checks for refunds, catalog, campaign history, freshness, exposure/assignment ordering and currency.

Readiness outputs are independent:

- `descriptive_ready`
- `prediction_ready`
- `behavioral_state_ready`
- `experiment_ready`
- `causal_history_ready`
- `economics_ready`

Orders can therefore be prediction-ready while economics remain unavailable, and campaigns can be descriptive while causal history is unavailable.

For a snapshot at `t`, source events require `event_time < t` and `observed_at <= t`. Suspicious source rows must be quarantined and reported, not silently discarded.
