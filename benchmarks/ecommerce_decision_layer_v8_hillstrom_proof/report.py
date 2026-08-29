"""Deterministic report generation from immutable V8 JSON results only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .integrity import FREEZE_MANIFEST, ROOT, VALIDATION_RESULT

ALLOWED_AUTHORITY = "REAL_RANDOMIZED_NET_REVENUE_AFTER_DECLARED_EMAIL_COST"
FORBIDDEN_AUTHORITIES = {
    "contribution_profit",
    "personalization_proven",
    "production_ready",
}


def authorize_claim(requested: str, verdict: str) -> str:
    if requested in FORBIDDEN_AUTHORITIES or requested != ALLOWED_AUTHORITY:
        raise ValueError(f"claim authority is prohibited: {requested}")
    if verdict != "PASS":
        raise ValueError("randomized net-revenue claim requires PASS")
    return requested


def _money(value: float) -> str:
    return f"${value:,.6f}"


def render_validation_report(result: dict[str, Any], freeze: dict[str, Any]) -> str:
    primary = result["primary"]
    ancova = result["secondary"]["lin_ancova"]
    aipw = result["secondary"]["cross_fitted_aipw"]
    bootstrap = result["secondary"]["arm_stratified_bootstrap"]
    mens_mean = result["arm_statistics"]["Mens E-Mail"]["mean_net_revenue"]
    control_mean = result["arm_statistics"]["No E-Mail"]["mean_net_revenue"]
    total_value = primary["total_incremental_value"]
    randomization_p = result["secondary"]["randomization_inference"]["two_sided_p_value"]
    consumed = str(result["validation_permanently_consumed"]).lower()
    lines = [
        "# Exergi V8 Validation Proof Report",
        "",
        f"Verdict: **{result['verdict']}**.",
        "",
        "## Frozen business decision",
        "",
        "Before VALIDATION was opened, V8 froze `STATIC_MENS_EMAIL_FOR_ALL_ELIGIBLE_CUSTOMERS`",
        "against `No E-Mail` BAU. The declared email cost was `$0.05` per assigned email customer.",
        "The primary unit-level outcome is spend minus that declared assignment cost.",
        "",
        "## Randomized validation result",
        "",
        f"- Analysis population: {result['analysis_population_n']:,} randomized customers",
        f"- Mens Email: {result['arm_statistics']['Mens E-Mail']['n']:,}",
        f"- No Email: {result['arm_statistics']['No E-Mail']['n']:,}",
        f"- Mens mean net revenue: {_money(mens_mean)}",
        f"- BAU mean net revenue: {_money(control_mean)}",
        f"- Primary incremental net revenue/customer: {_money(primary['point'])}",
        f"- Neyman standard error: {_money(primary['standard_error'])}",
        f"- Two-sided 95% CI: [{_money(primary['lower_95'])}, {_money(primary['upper_95'])}]",
        f"- Normal-approximation two-sided p-value: {primary['two_sided_p_value']:.12g}",
        "- Total incremental value in the primary validation population: "
        f"{_money(total_value)}",
        "",
        "The primary gate uses only the untransformed difference in randomized arm means and its",
        "two-sided Neyman 95% interval. No secondary analysis can change the verdict.",
        "",
        "## Frozen corroborating analyses",
        "",
        f"- Lin ANCOVA: {_money(ancova['point'])}, 95% CI "
        f"[{_money(ancova['lower_95'])}, {_money(ancova['upper_95'])}]",
        f"- Cross-fitted AIPW: {_money(aipw['point'])}, 95% CI "
        f"[{_money(aipw['lower_95'])}, {_money(aipw['upper_95'])}]",
        f"- Assignment randomization p-value: {randomization_p:.12g}",
        f"- Arm-stratified bootstrap: {_money(bootstrap['point'])}, 95% percentile CI "
        f"[{_money(bootstrap['lower_95'])}, {_money(bootstrap['upper_95'])}]",
        "",
        "Purchaser decomposition, preregistered nonzero winsorization, leave-top diagnostics and",
        "largest-observation influence are preserved in the machine-readable result.",
        "",
        "## Development versus validation",
        "",
        f"- DEVELOPMENT raw net uplift: {_money(result['development_comparison']['net_uplift'])}",
        f"- VALIDATION raw net uplift: {_money(primary['point'])}",
        "",
        "## Integrity and one-shot status",
        "",
        f"- Freeze commit: `{result['freeze_commit']}`",
        f"- Frozen source-tree SHA-256: `{freeze['source_tree_sha256']}`",
        f"- Validation permanently consumed: `{consumed}`",
        "- SEALED_TEST: untouched by V8 and still quarantined because historical row-0 was exposed",
        "- Buy Baits: unchanged",
        "",
        "## Claim authority and limitations",
        "",
        f"Authority: `{result['claim_authority']}`.",
        "",
        result["claim_text"],
        "",
        "Hillstrom records spend/revenue, not contribution profit. It lacks observed COGS,",
        "shipping, returns, payment fees and other variable costs. The `$0.05` cost is declared",
        "rather than an observed merchant ledger. This does not prove personalization, general",
        "merchant performance,",
        "autonomous decision safety or production readiness.",
        "",
    ]
    return "\n".join(lines)


def render_claim_card(result: dict[str, Any]) -> str:
    if result["verdict"] == "PASS":
        claim = result["claim_text"]
    else:
        claim = (
            "Hillstrom did not independently confirm the development-selected action. Exergi "
            "remains shadow-only, and the next evidence must come from a new randomized economic "
            "dataset or a merchant-approved prospective experiment."
        )
    return "\n".join(
        [
            "# Exergi V8 Claim Card",
            "",
            f"Verdict: **{result['verdict']}**",
            "",
            f"Authority: `{result['claim_authority']}`",
            "",
            claim,
            "",
            "Not authorized: contribution profit, personalized uplift, merchant generalization,",
            "autonomous safety, or production readiness.",
            "",
        ]
    )


def write_reports(result_path: Path = VALIDATION_RESULT) -> None:
    result = json.loads(result_path.read_text())
    freeze = json.loads(FREEZE_MANIFEST.read_text())
    (ROOT / "V8_VALIDATION_PROOF_REPORT.md").write_text(render_validation_report(result, freeze))
    (ROOT / "V8_CLAIM_CARD.md").write_text(render_claim_card(result))
    reproduction = "\n".join(
        [
            "# V8 Reproduction",
            "",
            "The validation outcome is permanently consumed. Do not rerun the raw-data analysis.",
            "Regenerate Markdown deterministically from the immutable result JSON with:",
            "",
            "```bash",
            ".venv/bin/python -m benchmarks.ecommerce_decision_layer_v8_hillstrom_proof.report",
            "```",
            "",
            "This command reads only `V8_VALIDATION_RESULT.json` and `V8_FREEZE_MANIFEST.json`; it",
            "does not open raw Hillstrom data or any held-out split.",
            "",
        ]
    )
    (ROOT / "V8_REPRODUCTION.md").write_text(reproduction)


if __name__ == "__main__":
    write_reports()
