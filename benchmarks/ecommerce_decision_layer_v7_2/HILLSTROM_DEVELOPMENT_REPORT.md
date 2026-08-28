# Hillstrom V7.2 Development Checkpoint

Status: **DEVELOPMENT ONLY — NO VALIDATION OR OFFICIAL FREEZE**.

Primary declared email cost: `$0.05` per recipient. Outcome is two-week
spend/revenue, not profit.

| Policy | Net value/customer | vs BAU | vs best static | 95% CI vs static |
|---|---:|---:|---:|---:|
| treat_all_mens | 1.645187 | 0.735009 | 0.000000 | [0.000000, 0.000000] |
| best_static | 1.645187 | 0.735009 | 0.000000 | [0.000000, 0.000000] |
| tweedie_t | 1.633220 | 0.723042 | -0.011967 | [-0.492335, 0.468401] |
| ridge_t | 1.547685 | 0.637507 | -0.097502 | [-0.802772, 0.607767] |
| x_learner_ridge | 1.539201 | 0.629023 | -0.105986 | [-0.811553, 0.599580] |
| r_learner_ridge | 1.536913 | 0.626735 | -0.108274 | [-0.814013, 0.597464] |
| two_part_logit_log_ridge | 1.520270 | 0.610092 | -0.124918 | [-0.819211, 0.569375] |
| dr_learner_ridge | 1.450454 | 0.540276 | -0.194733 | [-0.905353, 0.515886] |
| simple_rfm_affinity_segment | 1.388519 | 0.478341 | -0.256668 | [-0.982996, 0.469659] |
| extra_trees_t | 1.234467 | 0.324289 | -0.410720 | [-1.027233, 0.205792] |
| causal_forest_dr | 1.147947 | 0.237770 | -0.497240 | [-1.181306, 0.186826] |
| hist_gradient_t | 0.926662 | 0.016484 | -0.718525 | [-1.544094, 0.107043] |
| BAU | 0.910178 | 0.000000 | -0.735009 | [-1.738119, 0.268100] |
| huber_t | 0.910178 | 0.000000 | -0.735009 | [-1.738119, 0.268100] |
| random_forest_t | 0.889791 | -0.020387 | -0.755397 | [-1.507665, -0.003128] |
| honest_dr_policy_tree | 0.753323 | -0.156855 | -0.891864 | [-1.626439, -0.157289] |
| treat_all_womens | 0.742697 | -0.167480 | -0.902490 | [-1.840092, 0.035112] |

Development-selected best static: **MENS_EMAIL**.
Provisional personalized leader: **tweedie_t**.
Material observable heterogeneity: **False**.

The static Mens policy's point-estimate increment over BAU is 0.735009, with 95% CI
[-0.268100, 1.738119]. It is positive as a point estimate but not statistically decisive on the
inner held-out split. Tweedie's fold increment over static is positive in four of five folds, but one
large negative fold dominates; the overall interval crosses zero. This is not stable evidence of
personalization.

The static Mens point-estimate break-even contact cost is `$0.7850` per emailed customer. The
train-development static choice changes to No Email at the `$1.00` and `$2.00` grid points. The
full fixed cost grid and candidate-specific break-even values are in the JSON result.

## Integrity incident

During header inspection, row-0 was accidentally printed with outcomes. The existing
manifest assigns it to SEALED_TEST. It was never used for fitting or scoring, but the
future sealed set cannot honestly be called fully untouched. All subsequent
materialization parsed DEVELOPMENT rows only.
