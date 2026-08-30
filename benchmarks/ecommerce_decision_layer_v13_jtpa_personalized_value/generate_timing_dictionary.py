from __future__ import annotations

import csv
from pathlib import Path

from pandas.io.stata import StataReader

from .qualification import BASELINE, OUTCOME_SCHEMA, TIMING_DICTIONARY

POLICY_ALLOWLIST = {
    "site",
    "trtmnt",
    "bfcaruse",
    "bfeduca",
    "bfedcmpt",
    "bfgradhs",
    "bfeduged",
    "bfvococc",
    "bfabeesl",
    "bfassdeg",
    "bfbacdeg",
    "bftecdip",
    "bfmaster",
    "bfwforpy",
    "bfpayful",
    "bfpaylas",
    "bfhrslas",
    "bflookwk",
    "bfemploy",
    "bfwkswrk",
    "bfyrearn",
    "bfuncomp",
    "bfstwork",
    "bfhrswrk",
    "bfwage",
    "bfpayprd",
    "bfdayswk",
    "bfgrspay",
    "bfnetpay",
    "bfcuremp",
    "bflvwork",
    "bfreaslv",
    "bfjbclub",
}
ASSIGNMENT_FIELDS = {"ra_stat", "treatmt", "control", "ra_dt", "ramonth", "cohort"}
PROTECTED_FIELDS = {
    "age",
    "race",
    "sex",
    "trgt_grp",
    "adultm",
    "adultf",
    "youthm",
    "youthn",
    "white",
    "black",
    "hispanic",
    "native",
    "asian",
    "wht_blk",
    "w_b_his",
    "male",
    "female",
}
PII_FIELDS = {"ssn", "lname", "fname", "dob", "phonehom"}
UNKNOWN_FIELDS = {"radrc", "nea_stat", "bifid"}


def columns(path: Path) -> list[str]:
    reader = StataReader(path, convert_categoricals=False)
    return list(reader.read(1).columns)


def baseline_row(variable: str) -> dict[str, str]:
    if variable == "recid":
        timing, status, reason = (
            "ASSIGNMENT_ONLY",
            "IDENTIFIER_ONLY",
            "Stable public-use participant join key; never a model feature.",
        )
    elif variable in ASSIGNMENT_FIELDS:
        timing, status, reason = (
            "ASSIGNMENT_ONLY",
            "EVALUATOR_ONLY",
            "Created or recorded at random assignment.",
        )
    elif variable in PII_FIELDS:
        timing, status, reason = (
            "PRETREATMENT_ALLOWED",
            "FORBIDDEN_PII",
            "Collected before assignment but prohibited by policy governance.",
        )
    elif variable in PROTECTED_FIELDS:
        timing, status, reason = (
            "PRETREATMENT_ALLOWED",
            "AUDIT_ONLY_PROTECTED",
            "Pretreatment protected characteristic; fairness audit only.",
        )
    elif variable in UNKNOWN_FIELDS:
        timing, status, reason = (
            "UNKNOWN_FORBIDDEN",
            "FORBIDDEN_UNKNOWN",
            "Semantics or timing are not sufficiently documented for policy use.",
        )
    elif variable in POLICY_ALLOWLIST:
        timing, status, reason = (
            "PRETREATMENT_ALLOWED",
            "POLICY_ALLOWED",
            "Background Information Form field recorded before the assignment call.",
        )
    else:
        timing, status, reason = (
            "PRETREATMENT_ALLOWED",
            "NOT_SELECTED",
            "Documented BIF/telephone-file baseline field, excluded from the V13 allowlist.",
        )
    return {
        "source": "expbif.dta",
        "variable": variable,
        "timing_class": timing,
        "policy_status": status,
        "rationale": reason,
    }


def downstream_row(source: str, variable: str) -> dict[str, str]:
    if variable == "recid":
        timing, status, reason = (
            "ASSIGNMENT_ONLY",
            "IDENTIFIER_ONLY",
            "Stable join key only.",
        )
    elif source == "ppd_dat.dta" and variable != "bifrsp":
        timing, status, reason = (
            "POST_TREATMENT_FORBIDDEN",
            "FORBIDDEN_POST_TREATMENT",
            "Enrollment/service/activity record created after randomized offer.",
        )
    elif variable.startswith(("newern", "totern", "uiern")):
        timing, status, reason = (
            "OUTCOME_ONLY",
            "EVALUATOR_ONLY",
            "Post-assignment monthly earnings outcome.",
        )
    else:
        timing, status, reason = (
            "EVALUATOR_ONLY",
            "EVALUATOR_ONLY",
            "Sample/response indicator unavailable to the policy at assignment.",
        )
    return {
        "source": source,
        "variable": variable,
        "timing_class": timing,
        "policy_status": status,
        "rationale": reason,
    }


def main() -> None:
    rows = [baseline_row(variable) for variable in columns(BASELINE)]
    for source in ["earns2.dta", "boysern2.dta", "toterns.dta", "ppd_dat.dta"]:
        rows.extend(
            downstream_row(source, variable)
            for variable in columns(OUTCOME_SCHEMA / source)
        )
    source = "scaledui.dta"
    rows.extend(
        downstream_row(source, variable)
        for variable in columns(OUTCOME_SCHEMA / "analysis" / source)
    )
    TIMING_DICTIONARY.parent.mkdir(parents=True, exist_ok=True)
    with TIMING_DICTIONARY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source", "variable", "timing_class", "policy_status", "rationale"],
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
