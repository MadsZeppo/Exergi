from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .observed import ACTION_INDEX, ACTION_NAMES, ObservedCustomerPool, ObservedDecisionBatch

ROOT = Path(__file__).resolve().parent
FEATURE_NAMES = (
    "log_recency",
    "log_frequency",
    "log_historical_value",
    "category_affinity",
    "price_sensitivity",
    "purchase_cadence",
    "observed_return_rate",
    "email_fatigue",
    "sms_fatigue",
    "paid_fatigue",
    "session_intensity",
    "cart_intent",
    "lifecycle_new",
    "lifecycle_dormant",
    "week_sin",
    "week_cos",
    "macro_demand_index",
    "deliverability",
    "shipping_cost_index",
    "channel_cost_index",
    "inventory_pressure",
    "budget_remaining_share",
)

FAMILY_PARAMETERS = {
    "FASHION": {"aov": 78.0, "purchase_rate": 0.025, "margin": 0.45, "returns": 0.19},
    "BEAUTY_SUPPLEMENTS": {
        "aov": 45.0,
        "purchase_rate": 0.038,
        "margin": 0.58,
        "returns": 0.06,
    },
    "HOME_GOODS": {"aov": 120.0, "purchase_rate": 0.018, "margin": 0.50, "returns": 0.10},
    "MARKETPLACE": {"aov": 62.0, "purchase_rate": 0.031, "margin": 0.36, "returns": 0.12},
}


def _manifest() -> dict[str, object]:
    return json.loads((ROOT / "manifests/V14_SPLIT_MANIFEST.json").read_text(encoding="utf-8"))


def merchant_spec(merchant_id: str) -> dict[str, object]:
    manifest = _manifest()
    for split in ("development", "validation", "sealed_test"):
        for item in manifest[split]:
            if item["merchant_id"] == merchant_id:
                return item
    raise KeyError(merchant_id)


def generate_customer_pool(merchant_id: str) -> ObservedCustomerPool:
    spec = merchant_spec(merchant_id)
    family = str(spec["family"])
    params = FAMILY_PARAMETERS[family]
    rng = np.random.default_rng(int(spec["customer_seed"]))
    n = int(spec["eligible_customers"])
    lifecycle = rng.choice(5, n, p=[0.12, 0.45, 0.18, 0.20, 0.05]).astype(np.int8)
    recency = np.maximum(0.0, rng.lognormal(3.1, 1.0, n) * (1 + 0.45 * (lifecycle == 3)))
    frequency = rng.negative_binomial(2, 0.35, n).astype(float)
    historical = rng.lognormal(np.log(params["aov"] * 3.0), 1.0, n) * (frequency > 0)
    category = rng.integers(0, 8, n, dtype=np.int8)
    category_affinity = rng.beta(2.2, 2.5, n)
    price_sensitivity = rng.beta(2.0, 3.2, n)
    cadence = np.clip(rng.lognormal(np.log(28.0), 0.75, n), 1, 365)
    return_rate = np.clip(rng.beta(1.5, 10.0, n) * (params["returns"] / 0.12), 0, 0.8)
    email_fatigue = rng.beta(1.5, 5.0, n)
    sms_fatigue = rng.beta(1.3, 6.0, n)
    paid_fatigue = rng.beta(1.8, 4.5, n)
    session_intensity = rng.gamma(1.4, 0.65, n)
    cart_intent = rng.beta(1.6, 4.5, n)
    features = np.column_stack(
        [
            np.log1p(recency) / 6,
            np.log1p(frequency) / 4,
            np.log1p(historical) / 8,
            category_affinity,
            price_sensitivity,
            np.log1p(cadence) / 6,
            return_rate,
            email_fatigue,
            sms_fatigue,
            paid_fatigue,
            np.log1p(session_intensity) / 3,
            cart_intent,
            (lifecycle == 0).astype(float),
            (lifecycle == 3).astype(float),
            np.zeros(n),
            np.ones(n),
            np.ones(n),
            np.ones(n),
            np.ones(n),
            np.ones(n),
            np.zeros(n),
            np.ones(n),
        ]
    ).astype(np.float32)
    prefix = f"{merchant_id}_C"
    customer_ids = np.asarray([f"{prefix}{index:05d}" for index in range(n)])
    email = rng.random(n) < 0.82
    sms = rng.random(n) < 0.58
    paid = rng.random(n) < 0.76
    return ObservedCustomerPool(
        merchant_id=merchant_id,
        family=family,
        customer_ids=customer_ids,
        features=features,
        feature_names=FEATURE_NAMES,
        lifecycle=lifecycle,
        category=category,
        email_eligible=email,
        sms_eligible=sms,
        paid_eligible=paid,
    )


def world_for_week(week: int) -> str:
    spec = json.loads((ROOT / "configs/V14_DGP_SPEC.json").read_text(encoding="utf-8"))
    families = spec["world_families"]
    return str(families[(week - 1) % len(families)])


def decision_batch(
    pool: ObservedCustomerPool,
    week: int,
    *,
    batch_size: int = 400,
) -> ObservedDecisionBatch:
    spec = merchant_spec(pool.merchant_id)
    world = world_for_week(week)
    rng = np.random.default_rng(int(spec["event_seed"]) + week)
    size = 50 if world == "LIMITED_SAMPLE_POWER" else batch_size
    indices = rng.choice(len(pool.customer_ids), size=size, replace=False)
    x = pool.features[indices].copy()
    angle = 2 * np.pi * (week - 1) / 52
    x[:, 14] = np.sin(angle)
    x[:, 15] = np.cos(angle)
    x[:, 16] = 0.82 if world == "COMMON_SHOCK" else 1.0
    x[:, 17] = 0.35 if world == "DELIVERABILITY_FAILURE" else 1.0
    x[:, 18] = 1.45 if world in {"DELAYED_REFUNDS", "RETURN_DRIVEN_REVERSAL"} else 1.0
    x[:, 19] = 1.40 if world in {"CHANNEL_FATIGUE", "CHANNEL_SUBSTITUTION"} else 1.0
    x[:, 20] = 0.75 if world == "INVENTORY_CONSTRAINT" else 0.10
    x[:, 21] = 0.08 if world == "BUDGET_CONSTRAINT" else max(0.15, 1 - week / 60)
    eligible = np.ones((size, len(ACTION_NAMES)), dtype=bool)
    eligible[:, ACTION_INDEX["EMAIL_REMINDER"]] = pool.email_eligible[indices]
    eligible[:, ACTION_INDEX["EMAIL_10_PERCENT_DISCOUNT"]] = pool.email_eligible[indices]
    eligible[:, ACTION_INDEX["SMS_REMINDER"]] = pool.sms_eligible[indices]
    eligible[:, ACTION_INDEX["SMS_10_PERCENT_DISCOUNT"]] = pool.sms_eligible[indices]
    eligible[:, ACTION_INDEX["PAID_RETARGETING"]] = pool.paid_eligible[indices]
    eligible[:, ACTION_INDEX["EMAIL_PLUS_RETARGETING"]] = (
        pool.email_eligible[indices] & pool.paid_eligible[indices]
    )
    inventory_ok = rng.random(size) > (0.18 if world == "INVENTORY_CONSTRAINT" else 0.02)
    eligible[:, ACTION_INDEX["FREE_SHIPPING"]] &= inventory_ok
    eligible[:, ACTION_INDEX["EMAIL_10_PERCENT_DISCOUNT"]] &= inventory_ok
    eligible[:, ACTION_INDEX["SMS_10_PERCENT_DISCOUNT"]] &= inventory_ok
    cost_complete = np.ones_like(eligible)
    if world == "INCOMPLETE_COSTS":
        cost_complete[:, 1:-1] = False
    data_valid = world != "DATA_CORRUPTION"
    return ObservedDecisionBatch(
        merchant_id=pool.merchant_id,
        family=pool.family,
        week=week,
        customer_ids=pool.customer_ids[indices],
        features=x,
        feature_names=pool.feature_names,
        eligible_actions=eligible,
        cost_complete=cost_complete,
        data_valid=data_valid,
    )
