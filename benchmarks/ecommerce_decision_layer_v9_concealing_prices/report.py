"""Deterministic Markdown and HTML renderers from immutable V9 JSON."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .integrity import DEVELOPMENT_RESULT, ROOT


def _number(value: float, digits: int = 3) -> str:
    return f"{value:,.{digits}f}"


def render_development_report(result: dict[str, Any]) -> str:
    s1 = result["study1"]
    s3 = result["study3"]
    s1p = s1["primary"]
    s3p = s3["primary"]
    s1_break_even = s1["break_even_incremental_action_cost_ars_per_assigned_visitor"]
    folds = s3["secondary"]["fold_estimates"]
    fold_lines = "\n".join(
        f"- Fold {item['fold']}: {_number(item['point'])} ARS "
        f"[{_number(item['lower_95'])}, {_number(item['upper_95'])}]"
        for item in folds
    )
    return f"""# V9 development report

Status: `V9_DEVELOPMENT_COMPLETE_VALIDATION_CLOSED`

The procedure was frozen in commit `{result['preregistration_commit']}` before development
outcome access. Validation and SEALED_TEST remain closed.

## Study 1 — ordinary online store

- Evidence: `AGGREGATE_RANDOMIZED_FIELD_EVIDENCE`
- Primary: raw ARS sales revenue per assigned unique daily visitor, paired by date
- Development: {s1['development_dates']} paired dates
- Delayed minus immediate: **{_number(s1p['point'])} ARS**
- 95% CI: [{_number(s1p['lower_95'])}, {_number(s1p['upper_95'])}]
- Standard error: {_number(s1p['standard_error'])}
- Frozen development decision: `{s1['selection']}`
- Break-even differential action cost: {_number(s1_break_even)} ARS per assigned visitor

The point estimate is positive, so the preregistered rule permits a TEST freeze. It is not ACT:
the interval crosses zero, the paired randomization p-value is
{s1['secondary']['paired_sign_randomization_p_value']:.3f}, and the first/second-half estimates
are {_number(s1['secondary']['first_half']['point'])} and
{_number(s1['secondary']['second_half']['point'])} ARS. This is unstable development evidence.

## Study 3 — seven-email sales flyer

- Evidence: `REAL_RANDOMIZED_SALES_REVENUE`
- Primary: raw weekly ARS sales revenue per randomized recipient, assignment ITT
- Development: {s3['development_rows']:,} recipients
- Delayed/hide minus immediate/show: **{_number(s3p['point'])} ARS**
- 95% CI: [{_number(s3p['lower_95'])}, {_number(s3p['upper_95'])}]
- Standard error: {_number(s3p['standard_error'])}
- Frozen development decision: `{s3['selection']}`
- SRM p-value: {s3['diagnostics']['srm_p_value']:.3f}

The raw-revenue bootstrap interval is
[{_number(s3['secondary']['arm_stratified_bootstrap']['lower_95'])},
{_number(s3['secondary']['arm_stratified_bootstrap']['upper_95'])}] ARS. The purchase-rate,
units, log1p-revenue, and leave-top-0.1% checks all point against hiding price. Revenue is highly
sparse and heavy-tailed: {s3['diagnostics']['revenue_heavy_tail']['zero_fraction']:.1%} zeros,
with the top 1% accounting for
{s3['diagnostics']['revenue_heavy_tail']['top_1_percent_revenue_share']:.1%} of revenue.

Fold estimates:

{fold_lines}

Only one fold has a positive point estimate; the pooled primary result and all preregistered
distributional checks support freezing the immediate reference and testing `AVOID_DELAYED_PRICE`
on one-shot validation.

## Policy hierarchy

No personalized candidates were legal because the field files expose no lawful pretreatment
feature set. The development tournament therefore contains only:

1. immediate/reference in both contexts;
2. delayed/action-all in both contexts;
3. best static action selected separately by development;
4. the simple context-blind rule: keep immediate disclosure.

Study 1 advances delayed only as TEST. Study 3 keeps immediate/AVOID. No cost was invented and no
net-profit or contribution-profit claim is issued.
"""


def write_development_report() -> Path:
    result = json.loads(DEVELOPMENT_RESULT.read_text())
    path = ROOT / "V9_DEVELOPMENT_REPORT.md"
    path.write_text(render_development_report(result))
    return path


def render_dashboard(result: dict[str, Any]) -> str:
    rows = []
    for label in ("study1", "study3"):
        study = result["studies"][label]
        primary = study["primary"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(study['context'])}</td>"
            f"<td>{html.escape(study['frozen_policy'])}</td>"
            f"<td>{html.escape(study['validation_status'])}</td>"
            f"<td>{_number(primary['point'])} ARS</td>"
            f"<td>[{_number(primary['lower_95'])}, {_number(primary['upper_95'])}]</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Exergi V9 randomized decision proof</title><style>
body{{font-family:Inter,system-ui,sans-serif;max-width:1080px;margin:40px auto;
padding:0 24px;color:#171717}}
h1{{font-size:2.3rem}} .notice{{padding:16px;background:#f4f4f5;border-left:4px solid #52525b}}
table{{width:100%;border-collapse:collapse;margin-top:24px}}
th,td{{padding:14px;border-bottom:1px solid #ddd;text-align:left}}
.fine{{color:#666;line-height:1.55}} code{{background:#f4f4f5;padding:2px 5px}}</style></head><body>
<p>EXERGI · READ-ONLY IMMUTABLE EVIDENCE</p><h1>Contextual price-display decisions</h1>
<div class="notice">Randomized sales revenue in original Argentine pesos. Not contribution
profit, personalization, guaranteed profit, or general merchant proof.</div>
<table><thead><tr><th>Context</th><th>Frozen policy</th><th>Validation</th>
<th>Effect</th><th>95% CI</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p class="fine">Study 1 and Study 3 are two contexts within one retailer/package, not two
independent merchants. V8 Hillstrom remains a separate randomized net-revenue proof and was not
reopened or pooled with these ARS results.</p>
<p class="fine">Overall V9:
<code>{html.escape(result['classification'])}</code></p></body></html>"""
