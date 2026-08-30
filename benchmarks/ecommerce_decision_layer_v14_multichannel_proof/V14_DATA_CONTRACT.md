# Exergi V14 data and timing contract

All records use UTC timestamps and synthetic IDs scoped by merchant. Customer, order, event, assignment,
cost and outcome joins declare cardinality and fail closed on duplicates that violate their key contract.

Customer State is materialized strictly before eligibility. Adding future events, assignments, outcomes,
returns, costs or shocks must not change an earlier feature or decision hash. Post-treatment mediators are
not policy features.

Assignments require eligibility time, assignment time, action, known propensity, policy version and
source. Unmatured outcomes are `PENDING`, not zero. Customer and merchant identities are disjoint across
DEVELOPMENT, VALIDATION and SEALED_TEST.

Evaluator truth uses separate types and forbidden field names. Policy modules reject objects or serialized
payloads containing latent response, potential outcome, true CATE/action, future shock/return, response
parameter or oracle-value fields.
