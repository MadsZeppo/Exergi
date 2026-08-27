# Experiment Engine V1

Experiments freeze eligibility, arms, allocation, seed, outcome, horizon, alpha and power before assignment. HMAC-SHA256 over merchant, experiment and customer provides deterministic reproducible assignment. Exact assignment probabilities are stored.

Assignment and exposure are separate. Primary analysis is intention to treat. The implemented estimator is randomized difference in means with standard error and 95% confidence interval. The product also exposes binary and continuous-outcome sample-size functions. CUPED and AIPW are specified integration targets but are not yet completed in the product service.

The default is fixed horizon; the UI must not invite p-value peeking. Multi-arm schemas are implemented. Holm correction is not yet wired into the executable analysis and is therefore a remaining limitation.
