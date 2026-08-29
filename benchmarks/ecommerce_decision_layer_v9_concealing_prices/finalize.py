"""Generate post-reveal artifacts strictly from immutable V9 JSON results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .integrity import (
    DEVELOPMENT_RESULT,
    FREEZE_MANIFEST,
    ROOT,
    SPLIT_MANIFEST,
    load_json,
    sha256_file,
)
from .report import render_dashboard
from .validation_runner import study_files


def _write(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n")


def _n(value: float, digits: int = 3) -> str:
    return f"{value:,.{digits}f}"


def build_result() -> dict[str, Any]:
    development = load_json(DEVELOPMENT_RESULT)
    freeze = load_json(FREEZE_MANIFEST)
    split = load_json(SPLIT_MANIFEST)
    s1_files = study_files("study1")
    s3_files = study_files("study3")
    s1 = load_json(s1_files.result)
    s3 = load_json(s3_files.result)
    statuses = {s1["status"], s3["status"]}
    if "CONFIRMED_ACTION" in statuses and "CONFIRMED_AVOID" in statuses:
        classification = "CONTEXTUAL_DECISION_PROOF_PASS"
    elif statuses & {"CONFIRMED_ACTION", "CONFIRMED_AVOID"} and "CONTRADICTED" not in statuses:
        classification = "SECOND_RANDOMIZED_COMMERCE_PROOF_PASS"
    elif "CONTRADICTED" not in statuses:
        classification = "PARTIAL"
    else:
        classification = "FAIL"
    result: dict[str, Any] = {
        "schema_version": 1,
        "classification": classification,
        "final_status_line": f"V9_{classification}",
        "dataset_qualification": "QUALIFIED",
        "official_source": "https://osf.io/xt42w",
        "paper_doi": "10.1093/jcr/ucaf051",
        "raw_sha256": freeze["raw_sha256"],
        "preregistration_commit": freeze["preregistration_commit"],
        "freeze_commit": "1fd6c27",
        "freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST),
        "development_result_sha256": sha256_file(DEVELOPMENT_RESULT),
        "split_manifest_sha256": sha256_file(SPLIT_MANIFEST),
        "studies": {
            "study1": {
                **s1,
                "decision": "ABSTAIN",
                "development": development["study1"],
                "randomization_unit": "visitor/cookie encounter",
                "analysis_unit": "paired date block",
                "total_field_rows": 112,
                "total_date_blocks": 56,
                "validation_status": s1["status"],
                "validation_artifact_sha256": sha256_file(s1_files.result),
                "consumed_lock_sha256": sha256_file(s1_files.consumed),
                "sealed_status": "OMITTED_BY_PREREGISTRATION",
            },
            "study3": {
                **s3,
                "decision": "AVOID",
                "development": development["study3"],
                "randomization_unit": "recipient user_id",
                "analysis_unit": "randomized recipient",
                "total_recipients": 771_583,
                "split_counts": split["study3"]["row_counts"],
                "validation_status": s3["status"],
                "validation_artifact_sha256": sha256_file(s3_files.result),
                "consumed_lock_sha256": sha256_file(s3_files.consumed),
                "sealed_status": "UNOPENED",
            },
        },
        "contextual_contrast_passed": classification == "CONTEXTUAL_DECISION_PROOF_PASS",
        "personalization_tested": False,
        "contribution_profit_claimed": False,
        "action_cost_observed": False,
        "validation_consumed": {"study1": True, "study3": True},
        "sealed_test_opened": False,
        "v8_unchanged_and_not_reopened": True,
        "buy_baits_unchanged_and_not_reopened": True,
    }
    return result


def validation_report(result: dict[str, Any]) -> str:
    s1 = result["studies"]["study1"]
    s3 = result["studies"]["study3"]
    p1 = s1["primary"]
    p3 = s3["primary"]
    d1 = s1["development"]["primary"]
    d3 = s3["development"]["primary"]
    return f"""# V9 validation report

Status: `{result['classification']}`

Both policies were selected on DEVELOPMENT, hash-frozen in commit `{result['freeze_commit']}`,
and evaluated once on their untouched VALIDATION split. Reveal-start and permanent consumed
records exist for both studies. Study 3 SEALED_TEST remains unopened; Study 1 had no SEALED_TEST
by preregistration.

## Study 1 — ordinary online store

| Stage | Delayed minus immediate ARS revenue per assigned visitor | 95% CI |
|---|---:|---:|
| DEVELOPMENT | {_n(d1['point'])} | [{_n(d1['lower_95'])}, {_n(d1['upper_95'])}] |
| VALIDATION | {_n(p1['point'])} | [{_n(p1['lower_95'])}, {_n(p1['upper_95'])}] |

Frozen policy: `TEST_DELAYED_PRICE`. Validation status: `{s1['status']}`. Final product decision:
`ABSTAIN`. The point direction replicated, but the paired-date interval remains wide and crosses
zero. The action did not satisfy the preregistered ACT/confirmation gate. This is aggregate
date-level evidence and cannot support customer-level uncertainty or personalization.

## Study 3 — discount sales-email flyer

| Stage | Hide/delayed minus show/immediate ARS revenue per recipient | 95% CI |
|---|---:|---:|
| DEVELOPMENT | {_n(d3['point'])} | [{_n(d3['lower_95'])}, {_n(d3['upper_95'])}] |
| VALIDATION | {_n(p3['point'])} | [{_n(p3['lower_95'])}, {_n(p3['upper_95'])}] |

Frozen policy: `AVOID_DELAYED_PRICE`. Validation status: `{s3['status']}`. Final product decision:
`AVOID`. Equivalently, keeping prices visible improved held-out gross sales revenue by
**{_n(-p3['point'])} ARS per randomized recipient**, 95% CI
[{_n(-p3['upper_95'])}, {_n(-p3['lower_95'])}]. Purchase probability, units, log1p revenue,
the development-fixed leave-top sensitivity, bootstrap, and randomization inference agree in
direction. SRM p={s3['diagnostics']['srm_p_value']:.3f}.

## Economic interpretation

The package contains sales revenue, not margin, COGS, fulfillment, returns, payment fees, or
action cost. No cost was invented. Study 3's held-out break-even gross harm avoided is
{_n(s3['break_even_harm_avoided_ars_per_recipient'])} ARS per recipient. These ARS effects are
not pooled with Hillstrom's USD net-revenue effect.

## Overall

One context produced `CONFIRMED_AVOID`; the other stayed `INCONCLUSIVE`. Therefore V9 earns
`SECOND_RANDOMIZED_COMMERCE_PROOF_PASS`, not `CONTEXTUAL_DECISION_PROOF_PASS`.
"""


def claim_card(result: dict[str, Any]) -> str:
    s3 = result["studies"]["study3"]
    primary = s3["primary"]
    return f"""# V9 claim card

## Authorized claim

On untouched randomized validation recipients in Frávega's discount sales-email context,
Exergi's development-frozen policy correctly avoided hiding prices. Showing prices instead of
hiding them was associated with **{_n(-primary['point'])} ARS more gross sales revenue per
recipient**, 95% CI [{_n(-primary['upper_95'])}, {_n(-primary['lower_95'])}].

Authority: `REAL_RANDOMIZED_SALES_REVENUE`.

## Aggregate context that did not confirm

The ordinary-store Study 1 delayed-price TEST had a positive held-out point estimate but a wide
interval crossing zero. It remains `ABSTAIN/INCONCLUSIVE` under
`REAL_RANDOMIZED_AGGREGATE_REVENUE`.

## Not authorized

- contribution profit or observed profit;
- personalized policy value or Customer Twin targeting;
- proof across two independent merchants;
- a universal recommendation to show or hide prices;
- production readiness, guaranteed revenue, or autonomous action.

Overall: `{result['classification']}`.
"""


def limitations(result: dict[str, Any]) -> str:
    return f"""# V9 limitations

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
   contrast. The honest overall status is `{result['classification']}`.
6. Results remain in historical Argentine pesos. No current-currency conversion or inflation
   adjustment is used, and ARS is never pooled with the USD Hillstrom result.
7. Public OSF files state no explicit node license. Public readability is not treated as a broad
   commercial reuse license.
8. The web appendix was not present in the OSF folders and was subscriber-restricted on OUP.
   Official field codebooks, raw files, scripts, and paper were sufficient for the locked static
   estimands, but the missing public supplement limits procedural detail.
"""


def reproduction() -> str:
    return """# V9 reproduction

## Immutable chain

1. `b81fb2e` — reconcile V8 provenance without reopening V8 outcomes.
2. `4638172` — acquire/verify official OSF files, qualify studies, create outcome-isolated
   splits, and preregister the V9 procedure.
3. `1fd6c27` — record DEVELOPMENT, complete pre-reveal QA, freeze both policies, and pass the
   outcome-free dry run.
4. The result commit records reveal-start, sufficient statistics, immutable validation results,
   consumed locks, reports, and post-reveal QA.

## Commands

```bash
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.prepare
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.development
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.freeze
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.validation_runner
.venv/bin/python -m benchmarks.ecommerce_decision_layer_v9_concealing_prices.finalize
```

The validation command is intentionally no longer reproducible after consumption: a second run
must fail closed. Reports can be regenerated deterministically from immutable result JSON with
the finalization command; it reads no raw data.

QA commands:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
git diff --check
```
"""


def public_case_study(result: dict[str, Any]) -> str:
    s3 = result["studies"]["study3"]
    primary = s3["primary"]
    return f"""# Exergi public case study — when not to hide a sale price

Frávega randomized 771,583 email recipients between seeing sale prices in the email and having
to click through before seeing them. Exergi used only a preregistered DEVELOPMENT split to choose
a static policy. It froze `AVOID_DELAYED_PRICE` before validation.

On 192,994 untouched validation recipients, hiding prices reduced gross sales revenue by
{_n(-primary['point'])} ARS per recipient relative to showing prices. The 95% interval for the
harm from hiding was [{_n(-primary['upper_95'])}, {_n(-primary['lower_95'])}] ARS. The frozen
AVOID decision therefore confirmed.

In a second context from the same retailer, delayed disclosure had a positive held-out point
estimate but insufficient precision, so Exergi abstained. This distinction is the product
behavior: use a supported action where evidence clears the gate, and refuse precision where it
does not.

This is randomized sales-revenue evidence in historical ARS—not contribution profit,
personalized targeting, a two-merchant proof, or a guarantee for another webshop.
"""


def outreach_card(result: dict[str, Any]) -> str:
    s3 = result["studies"]["study3"]
    primary = s3["primary"]
    return f"""# Two independent randomized commerce decision proofs

## Hillstrom — email versus BAU

On untouched randomized validation customers, the V8 development-frozen email policy produced
`+$0.719312` net revenue per eligible customer after the declared email cost, with 95% CI
`[$0.219558; $1.219067]`.

## Concealing Prices — show versus hide price in a discount flyer

On untouched randomized validation recipients, the V9 development-frozen policy correctly chose
`AVOID` for hiding the price. Showing rather than hiding produced **{_n(-primary['point'])} ARS
more gross sales revenue per recipient**, 95% CI
[{_n(-primary['upper_95'])}, {_n(-primary['lower_95'])}].

These are independent randomized datasets and decision proofs, not pooled effects or proof for
every webshop. The first authority is randomized net revenue under a declared email cost; the
second is randomized gross sales revenue with no observed action cost.
"""


def finalize() -> dict[str, Any]:
    result = build_result()
    result_path = ROOT / "V9_RESULT.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    _write(ROOT / "V9_VALIDATION_REPORT.md", validation_report(result))
    _write(ROOT / "V9_CLAIM_CARD.md", claim_card(result))
    _write(ROOT / "V9_LIMITATIONS.md", limitations(result))
    _write(ROOT / "V9_REPRODUCTION.md", reproduction())
    _write(ROOT / "V9_PUBLIC_CASE_STUDY.md", public_case_study(result))
    _write(ROOT / "V9_OUTREACH_EVIDENCE_CARD.md", outreach_card(result))
    _write(ROOT / "V9_PROOF_DASHBOARD.html", render_dashboard(result))
    return result


if __name__ == "__main__":
    print(json.dumps(finalize(), indent=2, sort_keys=True))
