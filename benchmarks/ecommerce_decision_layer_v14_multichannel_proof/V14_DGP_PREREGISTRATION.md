# Exergi V14 DGP preregistration

Status: `NO_SYNTHETIC_OUTCOMES_GENERATED`

## Observable layer

The engine may receive only point-in-time pretreatment customer state, observable company/world state,
eligibility, actual randomized assignment, known logged propensity, actual mature costs and observed
mature outcomes. Customer State includes lifecycle, RFM/value, category and product affinity, price
sensitivity, channel eligibility, cadence, return propensity and fatigue.

## Evaluator layer

Latent response type, potential outcomes, true CATE, true best action, future shocks, future returns,
response parameters and oracle value are evaluator-only. The evaluator is a separate module and its
objects cannot be serialized into policy context.

The causal response functions are independently synthetic. Complete Journey and Online Retail II provide
aggregate observable marginal calibration only; they supply no causal effect, policy or cost truth.

## Required mechanisms

The 25 frozen world families cover no opportunity, homogeneous positive and harmful actions, profitable
static actions, material and sparse heterogeneity, channel substitution/fatigue, discount cannibalization,
pull-forward, delayed refunds, incomplete costs, shocks, seasonality, propensity/support failure, data
corruption, reversal, drift, unseen products, limited power, return reversal, deliverability, inventory,
budget and cold-start constraints.

The generator uses paired common random numbers for policy evaluation. DEVELOPMENT, VALIDATION and SEALED
occupy explicitly distinct response/shock parameter regions in `configs/V14_DGP_SPEC.json`, not merely
different seeds.
