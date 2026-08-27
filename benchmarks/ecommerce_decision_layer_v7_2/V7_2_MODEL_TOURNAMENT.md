# V7.2 Model Tournament

Status: **ENGINE IMPLEMENTED; REAL-DATA TOURNAMENT NOT AUTHORIZED**.

Implemented candidate families:

- per-arm Ridge;
- per-arm Random Forest;
- per-arm Extra Trees;
- per-arm HistGradientBoosting;
- per-arm Tweedie regression;
- per-arm Huber regression;
- two-part logistic purchase probability × log-Ridge positive spend with smearing correction.

Every candidate produces all-arm monetary predictions and supports strict K-fold nuisance
cross-fitting. The policy layer subtracts action-specific costs, filters governance-prohibited arms,
requires arm support and applies a lower-bound/materiality gate. Evaluation implements known-
propensity IPW, normalized Hájek and multi-arm DR/AIPW with ESS, maximum weights, clipping fraction
and cluster-aware uncertainty.

No winner is named. Doing so before complete Buy Baits/Dataset C authority and immutable manifests
would be model selection on an incomplete target.
