# V7.2 Model Tournament

Status: **BUY BAITS DEVELOPMENT TOURNAMENT RUN; OFFICIAL SELECTION NOT FROZEN**.

Compared policies include BAU, every governance-allowed treat-all arm, train-selected best static,
a device segment rule, per-arm Ridge/Random Forest/Extra Trees/Histogram Gradient/Huber,
logistic-times-positive-value hurdle, X learner, randomized R learner, known-propensity DR learner,
DR causal forest and shallow DR policy tree. Nuisance predictions are strict five-fold OOF on train;
held-out development rows are never used for fitting. Primary evaluation is known-propensity DR
value, not purchase prediction.

Outcome calibration is retained in
`results/buy_baits_development_tournament.json`, but cannot override policy value. The provisional
best personalized model by held-out value is Huber T; it does not beat BAU and its incremental CI
crosses zero. There is no legitimate personalized promotion and no official winner.

Tweedie was not run on the retailer-profit target because that target contains negative support;
silently shifting the outcome would change the economic estimand. This is reported as an invalid
candidate, not hidden as a model failure.
