# V7.3 Audit of the Existing Hillstrom Stability Gate

Diagnostic only. Hillstrom remains DEVELOPMENT-CONSUMED; VALIDATION and SEALED_TEST were not read.

The V7.2 rule uses five unstratified deterministic SHA-256 folds. It requires at least four positive folds, every leave-one-fold-out estimate positive, and no individual fold below -$0.05 net. Thus one fold below -$0.05 vetoes the action even when the aggregate adjusted lower bound is positive.

| Fold | Mens n/purchases/total | Control n/purchases/total | Net DIM | SE | 95% CI | Max | Leave top 1/5/10 | Max |SMD| |
|---:|---|---|---:|---:|---|---:|---|---:|
| 0 | 2131/25/$4306.54 | 2135/11/$906.51 | $1.5463 | $0.5693 | [$0.4306, $2.6621] | $499.00 | $1.3130/$0.4688/$0.1671 | 0.0431 |
| 1 | 2157/20/$2359.08 | 2250/20/$2708.91 | $-0.1603 | $0.4773 | [$-1.0958, $0.7753] | $499.00 | $0.0611/$-0.2232/$-0.1144 | 0.0297 |
| 2 | 2093/37/$4085.96 | 2163/22/$2377.01 | $0.8033 | $0.5261 | [$-0.2278, $1.8343] | $499.00 | $0.5657/$0.3756/$0.0547 | 0.0284 |
| 3 | 2139/33/$4503.91 | 2189/14/$1923.50 | $1.1769 | $0.5887 | [$0.0231, $2.3308] | $499.00 | $0.9445/$0.9483/$0.3112 | 0.0343 |
| 4 | 2135/18/$1610.10 | 2119/10/$1245.78 | $0.1162 | $0.3687 | [$-0.6063, $0.8388] | $499.00 | $0.3516/$0.2972/$0.1088 | 0.0478 |

Observed positive folds: `4/5`; minimum fold net: `$-0.160274`; every leave-one-fold-out estimate positive: `True`. The fixed gate therefore fails.

Top-observation contributions, purchase rates, arm-level means, ESS, numeric balance, and leave-top-k diagnostics are retained in `results/hillstrom_v72_fold_forensics.json`. No diagnostic is used to change V7.2 or select a V7.3 threshold.
