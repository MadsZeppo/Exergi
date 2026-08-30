# Exergi V14 calibration limitations

This checkpoint deliberately has narrow authority.

- Complete Journey is a single high-frequency grocery context; Online Retail II is a single UK non-store
  retailer with wholesale-like customers. Neither is a representative population of all Shopify stores.
- Neither source logs randomized multi-channel assignments or known action propensities.
- Neither source contains sufficient COGS, payment, fulfilment, shipping and channel-cost fields for
  contribution-profit reconstruction.
- Complete Journey has no authoritative returns. Online Retail II cancellations are only a return/refund
  proxy and do not establish physical-return maturity or cost.
- Both sources lack reliable email/SMS/paid-channel identity, consent, deliverability and send costs.
- Online Retail II has substantial missing customer IDs and exact duplicate rows. Identified-customer
  frequency and concentration are conditional on observed IDs.
- Empirical marginal calibration does not validate joint dependencies, treatment-effect distributions,
  policy value, safety behavior or cross-merchant transport.

Accordingly, V14 may use these aggregates to bound plausible observable commerce distributions only.
All synthetic causal response and cost components must be independently preregistered and clearly marked.
