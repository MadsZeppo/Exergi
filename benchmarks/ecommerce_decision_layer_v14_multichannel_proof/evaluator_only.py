from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dgp import FAMILY_PARAMETERS, merchant_spec, world_for_week
from .observed import ACTION_INDEX, ACTION_NAMES, LoggedDecisionBatch, ObservedDecisionBatch

DIRECT_COST = np.asarray([0.0, 0.02, 0.03, 0.06, 0.07, 0.02, 0.45, 0.04, 0.48, 0.0])
CONTACT_ACTIONS = np.asarray([False, True, True, True, True, True, True, True, True, False])
DISCOUNT_ACTIONS = np.asarray([False, False, True, False, True, False, False, False, False, False])


@dataclass(frozen=True)
class OracleBatch:
    latent_response_type: np.ndarray
    potential_gross_revenue: np.ndarray
    potential_discounts: np.ndarray
    potential_refunds: np.ndarray
    potential_shipping_revenue: np.ndarray
    potential_cogs: np.ndarray
    potential_payment_fees: np.ndarray
    potential_shipping_cost: np.ndarray
    potential_shipping_subsidy: np.ndarray
    potential_fulfilment_cost: np.ndarray
    potential_return_shipping_cost: np.ndarray
    potential_restocking_loss: np.ndarray
    potential_channel_cost: np.ndarray
    potential_switching_cost: np.ndarray
    potential_contribution_profit: np.ndarray
    true_best_action: np.ndarray


def _world_effect(world: str, x: np.ndarray, latent: np.ndarray) -> np.ndarray:
    n = len(x)
    effects = np.zeros((n, len(ACTION_NAMES)))
    intent = x[:, 11]
    price = x[:, 4]
    dormant = x[:, 13]
    effects[:, 1] = 0.25 + 0.55 * intent - 0.45 * x[:, 7]
    effects[:, 2] = 0.15 + 0.95 * price + 0.25 * dormant
    effects[:, 3] = 0.20 + 0.65 * intent - 0.60 * x[:, 8]
    effects[:, 4] = 0.10 + 1.05 * price + 0.20 * dormant
    effects[:, 5] = 0.20 + 0.70 * price
    effects[:, 6] = 0.15 + 0.75 * intent - 0.50 * x[:, 9]
    effects[:, 7] = 0.12 + 0.50 * intent
    effects[:, 8] = effects[:, 1] + effects[:, 6] - 0.20
    latent_modifier = np.select(
        [latent == 1, latent == 2, latent == 3, latent == 4, latent == 5, latent == 6],
        [0.75, -0.20, -0.90, 0.35 * price, 0.50 * intent, -0.50 * x[:, 7]],
        default=0.0,
    )
    effects[:, 1:9] += latent_modifier[:, None]
    if world == "NO_ACTIONABLE_OPPORTUNITY":
        effects[:, 1:9] = 0.0
    elif world == "HOMOGENEOUS_POSITIVE_ACTION":
        effects[:, 1] = 0.85
    elif world == "GLOBALLY_HARMFUL_ACTION":
        effects[:, 1:9] = -0.80
    elif world == "PROFITABLE_STATIC_ACTION":
        effects[:, 5] = 0.90
    elif world == "MATERIAL_CUSTOMER_HETEROGENEITY":
        effects[:, 1:9] *= np.where((intent + price)[:, None] > 0.85, 1.8, -0.35)
    elif world == "SPARSE_RESPONDERS":
        effects[:, 1:9] *= np.where((intent > 0.72)[:, None], 2.3, -0.15)
    elif world == "CHANNEL_SUBSTITUTION":
        effects[:, 1] += 0.65 * (x[:, 7] < x[:, 8])
        effects[:, 3] += 0.65 * (x[:, 8] <= x[:, 7])
        effects[:, 8] -= 0.75
    elif world == "CHANNEL_FATIGUE":
        effects[:, 1] -= 1.4 * x[:, 7]
        effects[:, 3] -= 1.5 * x[:, 8]
        effects[:, 6] -= 1.2 * x[:, 9]
    elif world == "DISCOUNT_CANNIBALIZATION":
        effects[:, 2] += 0.55 * price
        effects[:, 4] += 0.55 * price
    elif world == "PULL_FORWARD":
        effects[:, 1:9] += 0.35
    elif world == "COMMON_SHOCK":
        effects[:, 1:9] = 0.0
    elif world == "PROPENSITY_SUPPORT_FAILURE":
        effects[:, 1] += 0.50
    elif world == "ABRUPT_REVERSAL":
        effects[:, 1:9] *= -1.0
    elif world == "GRADUAL_DRIFT":
        effects[:, 1:9] *= 0.35
    elif world == "NEW_UNSEEN_PRODUCTS":
        effects[:, 1:9] *= 0.25
    elif world == "RETURN_DRIVEN_REVERSAL":
        effects[:, 2] += 0.75
        effects[:, 4] += 0.75
    elif world == "DELIVERABILITY_FAILURE":
        effects[:, [1, 2, 8]] = -0.15
    elif world == "NEW_MERCHANT_COLD_START":
        effects[:, 1:9] *= 0.20
    return effects


def potential_outcomes(batch: ObservedDecisionBatch) -> OracleBatch:
    spec = merchant_spec(batch.merchant_id)
    params = FAMILY_PARAMETERS[batch.family]
    truth_seed = int(spec["truth_seed"])
    rng = np.random.default_rng(truth_seed + batch.week)
    n, actions = len(batch.customer_ids), len(ACTION_NAMES)
    world = world_for_week(batch.week)
    latent_probabilities = [
        0.18,
        0.16,
        0.12,
        0.10,
        0.09,
        0.08,
        0.07,
        0.05,
        0.05,
        0.04,
        0.03,
        0.03,
    ]
    customer_index = np.asarray([int(value[-5:]) for value in batch.customer_ids])
    latent_pool = np.random.default_rng(truth_seed).choice(
        12, 20_000, p=latent_probabilities
    )
    latent = latent_pool[customer_index]
    x = batch.features
    baseline_logit = (
        np.log(params["purchase_rate"] / (1 - params["purchase_rate"]))
        + 0.55 * x[:, 2]
        + 0.85 * x[:, 11]
        - 0.35 * x[:, 0]
        + 0.18 * x[:, 15]
        + 0.35 * (x[:, 16] - 1.0)
    )
    effect = _world_effect(world, x, latent)
    purchase_probability = 1 / (1 + np.exp(-(baseline_logit[:, None] + effect)))
    purchase_draw = rng.random(n)[:, None]
    purchase = purchase_draw < purchase_probability
    order_value = np.broadcast_to(
        rng.lognormal(np.log(params["aov"]) - 0.35, 0.70, n)[:, None],
        (n, actions),
    )
    gross = purchase * order_value
    discounts = gross * DISCOUNT_ACTIONS * 0.10
    cogs = gross * (1 - params["margin"])
    payment = gross * 0.025
    fulfilment = purchase * 2.60
    shipping_cost = purchase * 5.40
    shipping_revenue = purchase * 4.90
    shipping_subsidy = purchase * (np.arange(actions) == ACTION_INDEX["FREE_SHIPPING"]) * 4.90
    return_probability = np.clip(
        params["returns"] + 0.15 * x[:, 6, None] + 0.08 * DISCOUNT_ACTIONS,
        0,
        0.75,
    )
    returned = rng.random(n)[:, None] < return_probability
    refunds = gross * returned
    return_shipping = returned * purchase * 6.50
    restocking = cogs * returned * 0.08
    channel = np.broadcast_to(DIRECT_COST, (n, actions)).copy()
    switching = purchase * ((np.arange(actions) == ACTION_INDEX["EMAIL_PLUS_RETARGETING"]) * 0.12)
    if world == "DISCOUNT_CANNIBALIZATION":
        discounts[:, [2, 4]] += gross[:, [2, 4]] * 0.08
    if world == "PULL_FORWARD":
        switching[:, 1:9] += gross[:, 1:9] * 0.12
    if world == "RETURN_DRIVEN_REVERSAL":
        refunds[:, [2, 4]] = np.maximum(refunds[:, [2, 4]], gross[:, [2, 4]] * 0.42)
    cp = (
        gross
        - discounts
        - refunds
        + shipping_revenue
        - cogs
        - payment
        - shipping_cost
        - shipping_subsidy
        - fulfilment
        - return_shipping
        - restocking
        - channel
        - switching
    )
    suppression = ACTION_INDEX["SUPPRESS_DO_NOT_CONTACT"]
    bau = ACTION_INDEX["BAU_NO_ACTION"]
    components = (
        gross,
        discounts,
        refunds,
        shipping_revenue,
        cogs,
        payment,
        shipping_cost,
        shipping_subsidy,
        fulfilment,
        return_shipping,
        restocking,
        channel,
        switching,
        cp,
    )
    for component in components:
        component[:, suppression] = component[:, bau]
    cp[~batch.eligible_actions] = -np.inf
    if world == "INCOMPLETE_COSTS":
        cp[~batch.cost_complete] = np.nan
    best = np.nanargmax(np.where(np.isfinite(cp), cp, -np.inf), axis=1).astype(np.int8)
    return OracleBatch(
        latent_response_type=latent,
        potential_gross_revenue=gross,
        potential_discounts=discounts,
        potential_refunds=refunds,
        potential_shipping_revenue=shipping_revenue,
        potential_cogs=cogs,
        potential_payment_fees=payment,
        potential_shipping_cost=shipping_cost,
        potential_shipping_subsidy=shipping_subsidy,
        potential_fulfilment_cost=fulfilment,
        potential_return_shipping_cost=return_shipping,
        potential_restocking_loss=restocking,
        potential_channel_cost=channel,
        potential_switching_cost=switching,
        potential_contribution_profit=cp,
        true_best_action=best,
    )


def randomized_log(batch: ObservedDecisionBatch) -> tuple[LoggedDecisionBatch, OracleBatch]:
    oracle = potential_outcomes(batch)
    spec = merchant_spec(batch.merchant_id)
    rng = np.random.default_rng(int(spec["assignment_seed"]) + batch.week)
    n = len(batch.customer_ids)
    world = world_for_week(batch.week)
    assignment = np.empty(n, dtype=np.int8)
    propensity = np.empty(n, dtype=float)
    for row in range(n):
        eligible = np.flatnonzero(batch.eligible_actions[row] & batch.cost_complete[row])
        if world == "PROPENSITY_SUPPORT_FAILURE":
            probabilities = np.full(len(eligible), 1 / len(eligible))
            if ACTION_INDEX["EMAIL_REMINDER"] in eligible:
                target = int(np.flatnonzero(eligible == ACTION_INDEX["EMAIL_REMINDER"])[0])
                probabilities *= 0.999 / max(1, len(eligible) - 1)
                probabilities[target] = 0.001
                probabilities /= probabilities.sum()
        else:
            probabilities = np.full(len(eligible), 1 / len(eligible))
        selected = int(rng.choice(eligible, p=probabilities))
        assignment[row] = selected
        propensity[row] = probabilities[int(np.flatnonzero(eligible == selected)[0])]
    observed_cp = oracle.potential_contribution_profit[np.arange(n), assignment]
    observed_revenue = oracle.potential_gross_revenue[np.arange(n), assignment]
    maturity = np.full(n, batch.week + (8 if world == "DELAYED_REFUNDS" else 4))
    if not batch.data_valid:
        propensity[:] = np.nan
    return (
        LoggedDecisionBatch(
            observed=batch,
            assignment=assignment,
            logged_propensity=propensity,
            gross_revenue=observed_revenue,
            contribution_profit=observed_cp,
            outcome_maturity_week=maturity,
        ),
        oracle,
    )
