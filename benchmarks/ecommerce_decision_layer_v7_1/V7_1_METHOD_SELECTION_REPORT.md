# V7.1 development-only method selection

Stage: O/P/Q development only. Source commit: `1ef3bd5d805ddf3d62422cca78918de8d8ebec93`.
Selected model: **`forest_t_learner`**. Configuration hash:
`19a556525687637c013f95e1331982c6ddaebadf851cb3860746ac9784f6a9dc`.

| Candidate | Eligible | Material Δ over static | Mean lower | Positive worlds | Observable capture | Nonmaterial promotion | Runtime |
|---|---|---:|---:|---:|---:|---:|---:|
| ridge T-learner | yes | 0.1988 | 0.0902 | 43.8% | 4.2% | 7.7% | 69.9s |
| forest T-learner | yes | **0.3260** | **0.2040** | **50.0%** | **26.7%** | 3.8% | 15.8s |
| X-learner | yes | 0.2899 | 0.1866 | 43.8% | 17.9% | 3.8% | 22.3s |
| R-learner | yes | 0.2604 | 0.1575 | 43.8% | 6.2% | 3.8% | 27.7s |
| DR-learner | yes | 0.2663 | 0.1645 | 43.8% | 8.6% | 3.8% | 30.4s |
| honest policy tree | yes | 0.2718 | 0.1695 | 43.8% | 14.6% | 3.8% | 24.0s |
| predefined segment policy | yes | 0.0445 | 0.0201 | 12.5% | -43.3% | 0.0% | 22.7s |
| causal forest DML | NOT EVALUATED | — | — | — | — | — | dependency unavailable |

Eligibility is only the development selector's safety filter: zero runtime failures, zero
unsupported ACT, acceptable null/harm and nonmaterial false-promotion rates. It is not a validation
PASS. The winner was selected by the frozen lexicographic rule after that filter.

All candidates used the same chronological outer base/gate/test split, economic net outcome,
support gate and held-out DR policy evaluator. R/DR nuisance predictions are three-fold
cross-fitted; no pseudo-outcome row is scored by a nuisance model fitted on that row. The causal
forest was not approximated under another implementation name.

## Interpretation

The forest is the best available development candidate, but only half of material-observable
development worlds had positive held-out increment and mean capture was 26.7%, below the frozen
50% validation gate. No R/S/T outcome was opened, so no validation claim is available. The model is
frozen for reproducibility, not approved for merchant personalization.
