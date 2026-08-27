"""Fixed Customer Twin query validation suite."""

from __future__ import annotations

from commercial_twin.customer_twin_core import EvidenceType, QueryClass

QUERY_BENCHMARK: tuple[tuple[str, QueryClass, EvidenceType], ...] = (
    (
        "What is happening with our customers right now?",
        QueryClass.DESCRIPTIVE,
        EvidenceType.OBSERVED_IDENTITY,
    ),
    ("What changed most this month?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    (
        "Is repeat purchase increasing or decreasing?",
        QueryClass.CHANGE,
        EvidenceType.OBSERVED_IDENTITY,
    ),
    ("Which cohorts are growing?", QueryClass.SEGMENT, EvidenceType.OBSERVED_IDENTITY),
    ("Which cohorts are shrinking?", QueryClass.SEGMENT, EvidenceType.OBSERVED_IDENTITY),
    ("Which customers are cooling?", QueryClass.SEGMENT, EvidenceType.OBSERVED_IDENTITY),
    ("Which customers are reactivating?", QueryClass.SEGMENT, EvidenceType.OBSERVED_IDENTITY),
    (
        "Which customers are most likely to buy next?",
        QueryClass.PREDICTIVE,
        EvidenceType.PREDICTIVE_ASSOCIATION,
    ),
    (
        "Which customers are least likely to return?",
        QueryClass.PREDICTIVE,
        EvidenceType.PREDICTIVE_ASSOCIATION,
    ),
    ("How is purchase frequency changing?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    ("How is AOV changing?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    (
        "How is customer value distribution changing?",
        QueryClass.CHANGE,
        EvidenceType.OBSERVED_IDENTITY,
    ),
    ("Which products are gaining affinity?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    ("Which products are losing affinity?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    ("Where are customers migrating?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    (
        "Which cohorts contribute most to revenue change?",
        QueryClass.SEGMENT,
        EvidenceType.OBSERVED_IDENTITY,
    ),
    ("Why is revenue down?", QueryClass.DRIVER, EvidenceType.DESCRIPTIVE_DECOMPOSITION),
    ("Are cancellations increasing?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    (
        "Which cohorts have the highest cancellation tendency?",
        QueryClass.CHANGE,
        EvidenceType.OBSERVED_IDENTITY,
    ),
    (
        "What will likely happen over the next 30 days?",
        QueryClass.PREDICTIVE,
        EvidenceType.PREDICTIVE_ASSOCIATION,
    ),
    (
        "Which customer changes deserve attention?",
        QueryClass.CHANGE,
        EvidenceType.OBSERVED_IDENTITY,
    ),
    ("Why is repeat revenue down?", QueryClass.DRIVER, EvidenceType.DESCRIPTIVE_DECOMPOSITION),
    (
        "Will cooling customers buy next month?",
        QueryClass.PREDICTIVE,
        EvidenceType.PREDICTIVE_ASSOCIATION,
    ),
    ("Did campaign X cause more purchases?", QueryClass.CAUSAL, EvidenceType.CAUSAL_RCT),
    ("What happens if we send campaign X?", QueryClass.SCENARIO, EvidenceType.CAUSAL_RCT),
    ("Should we test this offer?", QueryClass.DECISION, EvidenceType.CAUSAL_RCT),
    (
        "What happens if we use a 10% discount?",
        QueryClass.DECISION,
        EvidenceType.CAUSAL_OBSERVATIONAL,
    ),
    ("What is current customer value?", QueryClass.CHANGE, EvidenceType.OBSERVED_IDENTITY),
    ("Which cohort is growing fastest?", QueryClass.SEGMENT, EvidenceType.OBSERVED_IDENTITY),
    ("What happens if we target cooling customers?", QueryClass.SCENARIO, EvidenceType.CAUSAL_RCT),
)
