# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .qualification import ROOT

TOURNAMENT = ROOT / "V13_MODEL_TOURNAMENT.json"
PLACEBOS = ROOT / "V13_PLACEBO_RESULTS.json"
ACCESS = ROOT / "manifests" / "V13_DEVELOPMENT_ACCESS.json"
SOURCE = ROOT / "manifests" / "V13_SOURCE_MANIFEST.json"
SPLIT = ROOT / "manifests" / "V13_SPLIT_MANIFEST.json"

STATUS = "V13_DEVELOPMENT_NO_PERSONALIZED_POLICY_EARNED_REVEAL"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _model_rows(tournament: dict[str, Any]) -> str:
    rows: list[str] = []
    for name, result in sorted(
        tournament["models"].items(),
        key=lambda item: item[1]["versus_best_static"]["doubly_robust"]["point"],
        reverse=True,
    ):
        dr = result["versus_best_static"]["doubly_robust"]
        ipw = result["versus_best_static"]["hajek_ipw"]
        passed = sum(bool(value) for value in result["gates"].values())
        rows.append(
            f"| `{name}` | {_money(ipw['point'])} | {_money(dr['point'])} | "
            f"[{_money(dr['lower_95'])}, {_money(dr['upper_95'])}] | "
            f"{result['treatment_rate']:.1%} | {passed}/{len(result['gates'])} |"
        )
    return "\n".join(rows)


def _assert_inputs(
    tournament: dict[str, Any],
    placebos: dict[str, Any],
    access: dict[str, Any],
    split: dict[str, Any],
) -> None:
    if tournament["development_status"] != STATUS:
        raise RuntimeError("unexpected V13 development status")
    if tournament["earned_validation_reveal"]:
        raise RuntimeError("V13 result unexpectedly authorizes validation")
    if tournament["access_control"]["validation_outcomes_opened"]:
        raise RuntimeError("V13 tournament says validation outcomes were opened")
    if placebos["validation_outcomes_opened"]:
        raise RuntimeError("V13 placebo says validation outcomes were opened")
    if access["validation_outcomes_opened"] or access["validation_outcome_bytes_opened"] != 0:
        raise RuntimeError("V13 access record is not outcome-isolated")
    if split["validation_outcomes_opened"]:
        raise RuntimeError("V13 split manifest says validation outcomes were opened")
    if placebos["passed_both_placebos"]:
        raise RuntimeError("persisted placebo classification unexpectedly changed")
    if any(result["pre_placebo_pass"] for result in tournament["models"].values()):
        raise RuntimeError("a V13 candidate unexpectedly passed the preregistered pre-placebo gate")


def render_reports() -> dict[str, str]:
    tournament = _load(TOURNAMENT)
    placebos = _load(PLACEBOS)
    access = _load(ACCESS)
    source = _load(SOURCE)
    split = _load(SPLIT)
    _assert_inputs(tournament, placebos, access, split)

    best_name = tournament["best_challenger"]
    best = tournament["models"][best_name]
    dr = best["versus_best_static"]["doubly_robust"]
    ipw = best["versus_best_static"]["hajek_ipw"]
    bootstrap = tournament["best_challenger_bootstrap"]
    fold_positive = sum(value > 0 for value in best["fold_value_vs_static"])
    site_nonnegative = sum(value >= 0 for value in best["site_value_vs_static"].values())
    failed_gates = [name for name, passed in best["gates"].items() if not passed]
    model_rows = _model_rows(tournament)

    development = f"""# Exergi V13 DEVELOPMENT report

Status: `{STATUS}`

## Decision

No personalized JTPA offer policy earned a one-shot VALIDATION reveal. DEVELOPMENT selected
`{tournament['best_static']}` as the best legal static policy. The numerically highest challenger was
`{best_name}`, but it failed the frozen uncertainty, fold, site and placebo gates. No model freeze was
created, and VALIDATION remains closed.

## Randomized DEVELOPMENT sample

- Randomized people: {tournament['development']['n']:,}
- Control mean, 30-month earnings: {_money(tournament['development']['control_mean'])}
- Offer mean, 30-month earnings: {_money(tournament['development']['offer_mean'])}
- Raw offer-minus-control ITT: {_money(tournament['development']['raw_offer_minus_control'])}
- Frozen materiality threshold: {_money(tournament['development']['materiality_usd'])}
- Outcome authority: nominal USD earnings over months 1–30, not contribution profit

Treat-all did not beat BAU: the Hájek estimate was
{_money(tournament['static_treat_all_vs_bau']['hajek_ipw']['point'])} with 95% CI
[{_money(tournament['static_treat_all_vs_bau']['hajek_ipw']['lower_95'])},
{_money(tournament['static_treat_all_vs_bau']['hajek_ipw']['upper_95'])}].

## Frozen tournament

| Candidate | Hájek vs static | DR vs static | DR 95% CI | Offer rate | gates passed |
|---|---:|---:|---:|---:|---:|
{model_rows}

The best challenger estimated {_money(dr['point'])} per randomized person by DR and
{_money(ipw['point'])} by Hájek/IPW. The corresponding DR 95% CI was
[{_money(dr['lower_95'])}, {_money(dr['upper_95'])}], and the deterministic 1,000-replicate bootstrap
CI was [{_money(bootstrap['lower_95'])}, {_money(bootstrap['upper_95'])}]. The policy offered treatment
to {best['treatment_rate']:.1%} of people. These estimates are exploratory DEVELOPMENT diagnostics,
not validated policy value.

## Promotion-gate outcome

- Positive folds: {fold_positive}/5; required: at least 4/5
- Nonnegative sites: {site_nonnegative}/12; required: at least 8/12 and no site below the harm floor
- Effective sample size, offer action: {best['ipw_ess_treated_action']:.0f}
- Effective sample size, control action: {best['ipw_ess_control_action']:.0f}
- Failed gates: {', '.join(f'`{gate}`' for gate in failed_gates)}
- Treatment-shuffle p-value: {placebos['treatment_shuffle_within_site']['one_sided_p_value']:.6f}
- Outcome-shuffle p-value: {placebos['outcome_shuffle']['one_sided_p_value']:.6f}

The positive point estimate is therefore insufficient evidence. It is not a claim that personalization
works, and it does not authorize opening VALIDATION.
"""

    failure = f"""# Exergi V13 failure decomposition

Status: `{STATUS}`

## Primary failure

`INSUFFICIENT_STABLE_PERSONALIZED_POLICY_EVIDENCE`

The highest-ranked DEVELOPMENT challenger (`{best_name}`) had a positive DR point estimate of
{_money(dr['point'])} per randomized person, but its 95% lower bound was
{_money(dr['lower_95'])}. Only {fold_positive}/5 folds and {site_nonnegative}/12 sites were nonnegative.
Both preregistered placebo tests also failed to separate the observed value from their finite shuffle
nulls (treatment p={placebos['treatment_shuffle_within_site']['one_sided_p_value']:.6f}; outcome
p={placebos['outcome_shuffle']['one_sided_p_value']:.6f}).

## What failed

1. **Uncertainty:** the conservative lower bound was not above zero.
2. **Fold stability:** the candidate missed the frozen 4/5-positive-fold threshold.
3. **Site stability:** site effects were heterogeneous and breached the frozen rule.
4. **Placebos:** neither shuffle test met the frozen one-sided 0.05 threshold.

## What did not fail

- The source remained qualified for randomized earnings analysis.
- Assignment propensity, timing allowlist, outcome isolation and ESS checks passed.
- The system selected BAU rather than promoting an unsupported personalized policy.
- No VALIDATION or sealed outcome was opened.

## Scientific interpretation

This is a responsible DEVELOPMENT stop. It neither proves that all personalization is valueless nor
supports a positive personalized policy claim. A later version may use a different preregistered design
or independent dataset, but V13 thresholds, results and closed VALIDATION cannot be retuned or reused.
"""

    stop = f"""# Exergi V13 stop report

Final status: `{STATUS}`

- Best static policy: `{tournament['best_static']}`
- Best numerical challenger: `{best_name}`
- Personalized policy earned reveal: **no**
- Freeze created: **no**
- VALIDATION outcomes opened: **no**
- VALIDATION outcome bytes opened: **0**
- Sealed test: **not part of V13**
- Next authorized V13 action: **none**

V13 stops at DEVELOPMENT. The result is immutable after the completion commit and must not be retuned
against VALIDATION. Any subsequent benchmark must be a separately named and preregistered version.
"""

    stability_lines = "\n".join(
        f"| `{site}` | {_money(value)} |"
        for site, value in sorted(best["site_value_vs_static"].items())
    )
    stability = f"""# Exergi V13 stability report

Status: `{STATUS}`

## Fold stability

The five frozen fold estimates versus BAU were:

{', '.join(_money(value) for value in best['fold_value_vs_static'])}.

Only {fold_positive}/5 were positive; the preregistered requirement was 4/5.

## Site stability

| Site | DR value per person vs BAU |
|---|---:|
{stability_lines}

Only {site_nonnegative}/12 sites were nonnegative. This is evidence of material transport/stability risk,
not a basis for selecting favorable sites after observing outcomes.
"""

    fairness_lines = "\n".join(
        f"| `{group}` | {values['n']:,} | {values['treatment_rate']:.1%} | "
        f"{_money(values['value_vs_static_dr'])} |"
        for group, values in sorted(tournament["fairness_audit_best_challenger"].items())
    )
    fairness = f"""# Exergi V13 fairness and support audit

Status: `{STATUS}`

Protected attributes were excluded from policy features and used only after out-of-fold decisions were
frozen for reporting. These DEVELOPMENT subgroup estimates are descriptive and unvalidated.

| Reporting group | n | offer rate | DR value vs BAU |
|---|---:|---:|---:|
{fairness_lines}

Known-propensity IPW ESS was {best['ipw_ess_treated_action']:.0f} for rows assigned the policy's offer
action and {best['ipw_ess_control_action']:.0f} for rows assigned its control action. ESS passed, but
support alone cannot repair the failed uncertainty and stability gates.
"""

    reproduction = f"""# Exergi V13 reproduction

Status: `{STATUS}`

## Immutable inputs

- Official source archive SHA-256: `{source['archive']['sha256']}`
- `scaledui.dta` SHA-256: `{source['released_files']['scaledui.dta']}`
- Split hash: `{split['split_hash']}`
- Qualification commit: `{split['source_qualification_commit']}`
- Preregistration commit: `{access['source_preregistration_commit']}`
- DEVELOPMENT ID hash: `{split['development_id_hash']}`
- VALIDATION ID hash: `{split['validation_id_hash']}`

## Deterministic commands

```bash
python -m benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.tournament
python -m benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.placebo
python -m benchmarks.ecommerce_decision_layer_v13_jtpa_personalized_value.report
pytest -q tests/test_v13_jtpa_qualification.py tests/test_v13_jtpa_preregistration.py tests/test_v13_jtpa_materialization.py tests/test_v13_jtpa_development.py
```

The tournament and placebo commands are DEVELOPMENT-only. Do not create or run a V13 validation runner:
the frozen promotion gate failed. The report command reads only persisted result and manifest artifacts.
"""

    limitations = f"""# Exergi V13 limitations

Status: `{STATUS}`

- V13 measures randomized 30-month nominal-USD earnings, not merchant revenue or contribution profit.
- JTPA eligibility is a public-program offer, not a commerce action.
- The best personalized point estimate is statistically uncertain and unstable across folds and sites.
- Shuffle placebos did not support promotion.
- Protected-group summaries are post-policy diagnostics with limited subgroup precision.
- No validation result exists, because DEVELOPMENT did not earn a reveal.
- No result supports production deployment, merchant readiness or a general personalization claim.
"""

    qa: dict[str, Any] = {
        "access_control": {
            "development_outcome_rows_opened": access["development_outcome_rows_opened"],
            "validation_outcome_bytes_opened": access["validation_outcome_bytes_opened"],
            "validation_outcomes_opened": access["validation_outcomes_opened"],
            "validation_reveal_started": tournament["access_control"][
                "validation_reveal_started"
            ],
        },
        "checks": {
            "all_candidates_failed_pre_placebo_gate": not any(
                result["pre_placebo_pass"] for result in tournament["models"].values()
            ),
            "best_static_is_bau": tournament["best_static"] == "BAU_TREAT_NONE",
            "no_freeze_authorized": not tournament["earned_validation_reveal"],
            "outcome_shuffle_completed": placebos["outcome_shuffle"]["replicates"] == 20,
            "placebos_did_not_pass": not placebos["passed_both_placebos"],
            "treatment_shuffle_completed": (
                placebos["treatment_shuffle_within_site"]["replicates"] == 20
            ),
            "validation_remains_closed": (
                not access["validation_outcomes_opened"]
                and access["validation_outcome_bytes_opened"] == 0
            ),
        },
        "input_hashes": {
            "development_access": _sha256(ACCESS),
            "model_tournament": _sha256(TOURNAMENT),
            "placebo_results": _sha256(PLACEBOS),
            "source_manifest": _sha256(SOURCE),
            "split_manifest": _sha256(SPLIT),
        },
        "schema_version": 1,
        "status": STATUS,
    }

    return {
        "V13_DEVELOPMENT_REPORT.md": development,
        "V13_FAILURE_DECOMPOSITION.md": failure,
        "V13_STOP_REPORT.md": stop,
        "V13_STABILITY_REPORT.md": stability,
        "V13_FAIRNESS_AND_SUPPORT_AUDIT.md": fairness,
        "V13_REPRODUCTION.md": reproduction,
        "V13_LIMITATIONS.md": limitations,
        "V13_DEVELOPMENT_QA.json": json.dumps(qa, indent=2, sort_keys=True) + "\n",
    }


def write_reports() -> dict[str, str]:
    reports = render_reports()
    for name, content in reports.items():
        suffix = "" if content.endswith("\n") else "\n"
        (ROOT / name).write_text(content + suffix, encoding="utf-8")
    return reports


if __name__ == "__main__":
    write_reports()
