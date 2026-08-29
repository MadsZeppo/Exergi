# V9 randomization audit

Status: `QUALIFIED_BEFORE_OUTCOME_ANALYSIS`

## Study 1 — Frávega online store

The paper documents visitor-level simple random assignment through VTEX, 50/50 between
immediate and delayed price disclosure. A cookie preserved assignment on the same device;
cross-device returning visitors could receive a new assignment. The released field file is not
visitor-level: it contains 112 day×arm aggregates across electric kettles and espresso machines.

- True assignment unit: visitor/cookie encounter.
- Released analysis unit: `date_id × treatment`.
- V9 split and inferential unit: whole `date_id` block.
- Arm mapping: `0 = Immediate-PD`, `1 = Delayed-PD`.
- Reference: `IMMEDIATE_PRICE_DISCLOSURE`, the control and ordinary visible-price behavior.
- Both arms: present exactly once on each of 56 dates.
- Split overlap: zero dates.
- Unequal traffic: handled in the primary monetary estimand by normalizing each arm's daily raw
  revenue by its own assigned unique-daily-visitor count before pairing.
- ITT limitation: no stable visitor IDs are released, so cross-day repeat visitors, cross-device
  reassignment, delivered exposure, and customer-level contamination cannot be audited from raw
  rows. The claim is aggregate randomized field evidence, not customer-level policy value.
- Product/category and actual calendar date: not released in the field CSV; categories were
  collapsed by the replication package. Category heterogeneity cannot be reconstructed.

The deterministic split was locked without outcomes: the first 28 ordered `date_id` values are
DEVELOPMENT and the final 28 are VALIDATION. No SEALED_TEST was made because splitting 56 dates
into 28/14/14 would make held-out inference unnecessarily sparse.

## Study 3 — seven-email sales flyer

The paper documents recipient-level random assignment to immediate versus delayed price
disclosure for a seven-day flyer sequence. The released field file contains 771,583 rows and
771,583 unique `user_id` values.

- Randomization, analysis, and split unit: recipient `user_id`.
- Arm mapping: `0 = SHOW_PRICE_IN_EMAIL` (immediate),
  `1 = HIDE_PRICE_UNTIL_PRODUCT_PAGE` (delayed).
- Reference: show price/immediate, the control flyer format.
- Treatment probability: documented 50/50.
- Duplicate recipient IDs: 0.
- Deterministic split: SHA-256 50/25/25 with fixed seed.
- Split overlap: 0 hashed IDs.
- DEVELOPMENT: 385,603 recipients (192,580 immediate; 193,023 delayed).
- VALIDATION: 192,994 recipients (96,563 immediate; 96,431 delayed).
- SEALED_TEST: 192,986 recipients (96,360 immediate; 96,626 delayed).
- Primary causal population: every randomized recipient in the selected split, regardless of
  open, click, or purchase.
- `n_opens` is actually the number of product clicks across seven emails according to the
  codebook. It is post-treatment and prohibited from policy and adjustment.
- Delivery, bounce, unsubscribe, campaign/day, and product identifiers are not released. V9
  therefore uses assignment ITT and does not condition on delivered/opened/clicked status.

The observed whole-file arm allocation is close to 50/50. Formal SRM and outcome missingness are
computed only inside the eligible split at its authorized analysis stage.

## Qualification conclusion

Both studies satisfy the 11-item V9 qualification contract. Study 1 qualifies only as
`AGGREGATE_RANDOMIZED_FIELD_EVIDENCE`; Study 3 qualifies as individual randomized field evidence
for a static decision. Neither dataset qualifies for personalization because neither exposes at
least five lawful pretreatment features.
