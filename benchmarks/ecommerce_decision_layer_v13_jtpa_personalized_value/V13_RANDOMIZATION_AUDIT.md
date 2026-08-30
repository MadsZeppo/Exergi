# V13 JTPA randomization audit

Status: `PASS_FOR_RANDOMIZED_OFFER_ITT`

## Design and assignment

The randomization unit is the individual eligible JTPA applicant. After staff assessed eligibility and
recommended a service strategy, the study's centralized telephone system assigned the applicant to:

- `RA_STAT=1`: eligible to receive JTPA Title II services (randomized offer);
- `RA_STAT=2`: barred from JTPA services for 18 months (BAU/control).

The estimand is intention-to-treat for the randomized offer. Enrollment, attendance, service receipt,
training completion and placement are post-treatment and forbidden. The normal propensity was 2/3.
Five SDAs temporarily used 3:1 or 6:1; the official 30-month analysis randomly removed the extra
treated observations before analysis to restore the 2:1 design.

## Participant identity and population

- Full randomized file: 20,601 rows; 20,601 unique nonblank `RECID`; zero duplicates.
- Primary V13 population: 15,134 unique people in both the official 30-month analysis sample and the
  official 12-site `SCALEDUI` file.
- Assignment: 10,145 offer; 4,989 control; observed offer rate 0.670345.
- Target-group counts for reporting only: 4,850 adult men, 5,822 adult women, 2,457 female youths,
  and 2,005 male youths.

The 12-site restriction avoids using the survey-only four sites and avoids the post-assignment male-youth
arrestee split as a policy/evaluation selection rule. The official report documents that the retained
30-month sample exclusions were applied symmetrically or restored assignment symmetry.

## SRM and balance

Against the documented 2:1 propensity, the primary sample SRM statistic is 0.921402 with
`p=0.337107`: PASS. Across 4,857 categorical indicators generated from the 33 policy-eligible raw
baseline fields, the maximum absolute standardized mean difference is 0.063242; none exceeds 0.10.
Protected characteristics were checked separately for audit but are not policy features.

## Propensity and support contract

The frozen primary propensity is `P(offer)=2/3` and `P(control)=1/3`. It is not estimated from outcomes.
The policy must report treatment rate, IPW/DR effective sample size, site support and subgroup support.
Observed participation is not a treatment definition and may never replace randomized assignment.
