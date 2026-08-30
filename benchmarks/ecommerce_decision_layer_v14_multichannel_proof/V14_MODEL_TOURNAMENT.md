# V14 DEVELOPMENT model tournament

| Candidate | non-BAU rate | DR value vs BAU/customer | DR 95% CI |
|---|---:|---:|---:|
| `BEST_STATIC` | 0.0% | $0.0000 | [$0.0000, $0.0000] |
| `RULE_SEGMENT_POLICY` | 17.6% | $0.0056 | [$-0.1036, $0.1149] |
| `REGULARIZED_LINEAR_T_LEARNER` | 48.0% | $-0.1277 | [$-0.3181, $0.0626] |
| `TREE_T_LEARNER` | 65.0% | $0.1306 | [$-0.0871, $0.3484] |
| `FOREST_T_LEARNER` | 50.5% | $-0.1033 | [$-0.3004, $0.0939] |
| `X_LEARNER` | 46.6% | $-0.1083 | [$-0.2985, $0.0819] |
| `R_LEARNER` | 39.8% | $-0.0578 | [$-0.2318, $0.1162] |
| `DR_LEARNER` | 40.9% | $0.0573 | [$-0.1255, $0.2401] |
| `CAUSAL_FOREST_EQUIVALENT` | 49.9% | $0.0657 | [$-0.1105, $0.2418] |
| `CONSERVATIVE_ENSEMBLE` | 33.5% | $0.0182 | [$-0.1510, $0.1874] |

Selection used only held-out known-propensity contribution-profit estimates. Oracle truth was attached
only after `BEST_STATIC` and all predictions were frozen. Complexity was promoted only if its held-out 95%
lower bounds beat best static under both Hájek/IPW and DR.
