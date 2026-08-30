# V12 Pennsylvania randomization audit

Status: `RANDOMIZATION_DOCUMENTED_PUBLIC_USE_IDENTITY_INSUFFICIENT`

## Verified design

The official Pennsylvania final report and public-use documentation establish:

- randomization unit: an eligible UI claimant;
- control: `tg = 0`;
- treatments: `tg = 1..6`;
- assignment used the last two digits of Social Security numbers within weekly office samples;
- claimant allocation proportions varied by treatment and time;
- treatment 6 allocation ended in July 1989;
- treatment 1 allocation increased in October 1989 after preliminary demonstration results;
- the analysis population required a selected claimant subsequently to claim a waiting or first
  compensated week;
- 94% of treatment-group members in that analysis population received orientation/the offer.

Treatment mapping:

| Arm | Offer |
|---|---|
| 0 | Control, no bonus offer |
| 1 | 3× WBA, 6-week qualification, workshop offer |
| 2 | 3× WBA, 12-week qualification, workshop offer |
| 3 | 6× WBA, 6-week qualification, workshop offer |
| 4 | 6× WBA, 12-week qualification, workshop offer |
| 5 | Initially 6× WBA then declining, 12-week qualification, workshop offer |
| 6 | 6× WBA, 12-week qualification, no workshop offer |

The records header contains `tg` plus `t0..t6`, but no persistent claimant ID. The internal design
used Social Security numbers; those identifiers are not in the public records file.

## Hard qualification failure

Without a released claimant identifier V12 cannot verify:

- one row and one assignment per claimant;
- duplicate or repeated claimants;
- a claimant-level deterministic 60/40 hash split;
- zero claimant overlap;
- claimant-level bootstrap clusters;
- an append-only assignment identity across file formats.

Using row order as an invented ID would not be a persistent claimant ID and is prohibited.

The survey file has a survey respondent `id`, but it is not a join key in the records file. More
importantly, bonus recipients were selected for interview with certainty and were oversampled based
on a post-treatment event. Published weights target descriptive treatment-group composition; they
do not turn the survey into the preregistered, untouched primary randomized population required for
personalized policy evaluation.

## Assignment probabilities

The procedure and target allocations are documented, but the allocation changed over time and the
public file does not release the per-claimant randomization key or exact assignment probability.
Assuming equal 1/7 propensity would be false. Empirical arm proportions cannot repair the missing
claimant identity or recover exact design probabilities without additional assumptions.

Conclusion: the experiment itself was randomized, but the public release cannot satisfy V12's
claimant-level integrity contract. No outcome analysis is authorized.
