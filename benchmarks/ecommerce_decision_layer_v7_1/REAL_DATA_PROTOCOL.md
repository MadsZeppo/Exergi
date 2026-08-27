# V7.1 real-data capability protocol

Frozen before V7.1 real-data execution. These datasets do not tune synthetic policy thresholds.

## Hillstrom

- Use all 64,000 rows and all three randomized arms.
- Primary estimand: multi-arm ITT for spend and conversion.
- Stable row-hash 60/20/20 train/development/test for policy learning.
- Compare control, best static arm, fixed RFM/business segments and learned policy.
- Spend is revenue, not contribution profit. A separate scenario subtracts a declared $0.50 contact
  cost and assumes no margin transformation; it cannot support a real profit claim.

## Criteo Uplift V2.1

- Verify full 13,979,592-row file and publisher SHA-256.
- Use a fixed, outcome-independent hash subsample where `hash(row_id, seed=202608271) mod 14 == 0`,
  expected near 1,000,000 rows. This bounds memory on the 8 GB deployment reference machine while
  preserving randomized assignment independently of outcomes.
- Record the exact selected row count and SHA-256 of selected row IDs.
- `treatment` is ITT assignment. `exposure` is post-assignment and forbidden from treatment and
  features.
- Report conversion/visit ATE, calibration, uplift ranking, held-out policy value, best static and
  treatment shuffle. No revenue or profit claim.

## Open Bandit

- Use both locally available publisher random and Bernoulli-TS `all` logs.
- The local archive contains 10,000-row quick samples, not the full 26M-row release. Run DM, IPS,
  SNIPS, DR and Switch-DR with documented propensities and report this limitation.
- Evaluate BTS click value against random-policy empirical click reference, ESS and overlap.
- Click authority only; no commercial-value claim.

## X5 RetailHero

- Use the complete local uplift label file and deterministic customer aggregates where practical.
- Assignment provenance remains `UNKNOWN_ASSIGNMENT`.
- Ranking/feature robustness only; no causal, revenue or profit PASS.

Any unavailable full release is reported as unavailable, never silently replaced by synthetic data.

