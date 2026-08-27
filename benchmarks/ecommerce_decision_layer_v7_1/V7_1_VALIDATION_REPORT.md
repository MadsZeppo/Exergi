# Exergi V7.1 validation status

Status: **NOT OPENED — V7.1 FAIL**.

The preregistered sequential assurance tournament failed its stop-latency and avoidable
post-observable-loss gates before R/S/T were opened. Under the frozen protocol, validation cannot
legitimately rescue that failure. R/S/T therefore remain unopened and Pack U remains
`SEALED_NOT_MATERIALIZED`.

No validation metric is reported because no validation outcome was read. This is a procedural
failure stop, not missing data silently interpreted as a pass.
