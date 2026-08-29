# V8 Development Reconstruction

Status: **MATCH — policy reconstructed, not reselected**.

The immutable DEVELOPMENT materialization contains 32,233 rows. 
Only DEVELOPMENT was read; VALIDATION and SEALED_TEST remained closed.

- Frozen policy: `STATIC_MENS_EMAIL_FOR_ALL_ELIGIBLE_CUSTOMERS`
- Raw gross Mens-minus-control uplift: `$0.738949792549`
- Raw net uplift after the frozen $0.05 cost: `$0.688949792549`
- Raw net 95% CI: `[$0.239413795073, $1.138485790025]`
- Lin ANCOVA net point: `$0.675671928737`
- Cross-fitted AIPW net point: `$0.670008310643`
- Personalized challenger promoted over static: no

V7.2 remains historically INCONCLUSIVE under its broader stability contract. V8 does not
rewrite that decision; it freezes the already-observed static Mens candidate for a
narrower independent randomized confirmation.
