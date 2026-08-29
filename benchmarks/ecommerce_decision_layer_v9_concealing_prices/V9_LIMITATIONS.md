# V9 limitations

1. Study 1 exposes only day×arm aggregates. Visitor IDs, actual dates, categories, and
   repeat/cross-device behavior are unavailable; 28 validation dates yield low precision.
2. Study 3 exposes recipient assignment and weekly outcomes but no lawful pretreatment feature
   set, delivery/bounce/unsubscribe logs, campaign/day identifiers, product mix, margin, returns,
   or action cost. It tests only a static assignment ITT decision.
3. Revenue is sparse and heavy-tailed. The raw-mean primary estimand was preserved; robustness
   checks agree for Study 3 but do not make the monetary distribution well behaved.
4. Both field studies come from one retailer and one paper/package. They are distinct contexts,
   not independent merchants.
5. Study 1 did not pass confirmation, so V9 does not establish the requested full contextual
   contrast. The honest overall status is `SECOND_RANDOMIZED_COMMERCE_PROOF_PASS`.
6. Results remain in historical Argentine pesos. No current-currency conversion or inflation
   adjustment is used, and ARS is never pooled with the USD Hillstrom result.
7. Public OSF files state no explicit node license. Public readability is not treated as a broad
   commercial reuse license.
8. The web appendix was not present in the OSF folders and was subscriber-restricted on OUP.
   Official field codebooks, raw files, scripts, and paper were sufficient for the locked static
   estimands, but the missing public supplement limits procedural detail.
