# Merchant Validation V1 Database Schema

Migration `0001_merchant_validation_v1` creates 34 PostgreSQL tables:

- tenancy and connections: `organizations`, `merchants`, `data_connections`, `sync_runs`;
- immutable provenance: `raw_source_records`;
- commerce: `customers`, `customer_identities`, `products`, `variants`, `orders`, `order_lines`, `refunds`, `return_lines`;
- behavior and campaigns: `behavior_events`, `campaigns`, `campaign_events`;
- economics: `cost_records`;
- trust and state: `data_health_runs`, `data_health_checks`, `customer_state_snapshots`, `population_state_snapshots`, `model_training_runs`;
- decisions: `opportunities`, `opportunity_evidence`, `action_candidates`;
- experiments: `experiments`, `experiment_arms`, `experiment_assignments`, `experiment_exposures`, `experiment_outcomes`, `experiment_results`;
- learning and operations: `merchant_learning_records`, `jobs`, `audit_log`.

High-volume event/order lookup paths are indexed. IDs are UUIDs; timestamps use `timestamptz`; currencies are required for monetary source records. Source versions are idempotent by source identity plus payload hash. Snapshot and result tables append versions instead of overwriting history.

`DATABASE_URL` is mandatory for runtime configuration. SQLite is not a supported production fallback.
