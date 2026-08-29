# V10 MT-LIFT randomization audit

Status: `NOT_CAUSALLY_QUALIFIED_BEFORE_OUTCOMES`

## What the official sources establish

The official README says coupon treatments were randomly assigned in randomized controlled
trials and describes five anonymous treatment labels (`0` through `4`), 99 anonymous features,
and click/conversion labels. The paper:

- defines `t = 0` as control and `t = 1..K` as treatment in its formal setup;
- describes released samples/instances from Meituan coupon RCTs;
- represents generic feature block `X` upstream of treatment and outcomes, with treatment
  independent of `X`;
- says the last week was used as test and the remaining period as train;
- reports five treatment options and approximately 5.5 million instances.

Together, these support `treatment = 0` as the intended control and support the claim that the
released observations came from randomized coupon assignment at the sample/impression level.

## What the official sources do not establish

| Required fact | Audit result |
|---|---|
| Persistent randomization unit | Not identified. The paper says sample/instance/impression but does not disclose a stable user or assignment ID. |
| Repeat-user structure | Unknown and unauditable; no documented identifier or clustering key. |
| Coupon definitions | Arms 1–4 are only anonymous treatment labels; coupon content and intensity are absent. |
| Assignment probabilities | Not published. Equal `1/5` assignment must not be assumed. |
| Feature-level timing | No codebook, names, or timestamps for `f0`–`f98`. The generic causal graph is insufficient to verify every released column. |
| Official code | No implementation code is present in the repository; only README documentation is published. |
| Raw randomization checks | Impossible because official `train.csv` and `test.csv` were not obtainable. |
| TEST randomization in bytes | The paper implies the temporal TEST slice comes from the RCT data, but this cannot be checked against raw rows. |

All `f0`–`f98` are therefore `UNKNOWN_FORBIDDEN` for this V10 checkpoint. There is no feature
allowlist.

## Contamination warning

Official GitHub issue 2 reports a large `f50` distribution difference between treatment 0 and
nonzero treatments. This third-party report is not proof of confounding. It is an unresolved
diagnostic that would require raw balance, treatment-predictability, propensity, SRM, and
cluster-aware checks. No maintainer explanation was present.

## Qualification decision

V10 cannot verify the randomization unit, repeat exposure structure, feature-level timing, or
raw integrity. Under the mission's hard stop rules it receives no causal-personalization claim
authority. DEVELOPMENT and TEST outcomes remain unopened; no preregistration, tournament,
freeze, dry run, reveal, or result artifact was created.

Final classification: `V10_DATASET_NOT_CAUSALLY_QUALIFIED`.
