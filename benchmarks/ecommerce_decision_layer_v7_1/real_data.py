"""Claim-bounded V7.1 capability runs on locally available real datasets."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

from decision_engine.datasets.criteo_uplift import CriteoUpliftAdapter
from decision_engine.datasets.hillstrom import CONTROL, MENS, WOMENS, HillstromDataset
from decision_engine.datasets.x5_retailhero import X5RetailHeroAdapter

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
OUTPUT = ROOT / "results" / "real_data_capabilities.json"
REPORT = ROOT / "V7_1_REAL_DATA_REPORT.md"


def _normal_interval(effect: float, se: float) -> tuple[float, float]:
    critical = float(norm.ppf(0.975))
    return effect - critical * se, effect + critical * se


def _difference(values: np.ndarray, treatment: np.ndarray) -> dict[str, object]:
    treated = values[treatment]
    control = values[~treatment]
    effect = float(np.mean(treated) - np.mean(control))
    se = float(
        np.sqrt(np.var(treated, ddof=1) / len(treated) + np.var(control, ddof=1) / len(control))
    )
    return {"effect": effect, "standard_error": se, "interval": _normal_interval(effect, se)}


def run_hillstrom() -> dict[str, object]:
    frame = HillstromDataset(REPOSITORY / "data/raw/hillstrom/hillstrom.csv").load_rct()
    row_id = frame["row_id"].to_numpy()
    bucket = (row_id * 2_654_435_761 % 100).astype(int)
    train = bucket < 60
    test = bucket >= 80
    treatment_text = frame["treatment"].to_numpy()
    spend = frame["spend"].to_numpy().astype(float)
    conversion = frame["conversion"].to_numpy().astype(float)
    arm_results: dict[str, object] = {}
    for arm in (MENS, WOMENS):
        subset = np.isin(treatment_text, [CONTROL, arm])
        assigned = treatment_text[subset] == arm
        arm_results[arm] = {
            "spend_itt": _difference(spend[subset], assigned),
            "conversion_itt": _difference(conversion[subset], assigned),
        }
    development = (bucket >= 60) & (bucket < 80)
    development_means = {
        arm: float(np.mean(spend[development & (treatment_text == arm)]))
        for arm in (CONTROL, MENS, WOMENS)
    }
    best_static = max(development_means, key=development_means.__getitem__)
    control_test = float(np.mean(spend[test & (treatment_text == CONTROL)]))
    static_test = float(np.mean(spend[test & (treatment_text == best_static)]))

    features = frame.select(HillstromDataset.feature_columns(frame)).to_dummies()
    x = features.to_numpy().astype(float)
    arm_models: dict[str, tuple[RandomForestRegressor, RandomForestRegressor]] = {}
    for index, arm in enumerate((MENS, WOMENS)):
        subset = train & np.isin(treatment_text, [CONTROL, arm])
        assigned = treatment_text[subset] == arm
        x_subset = x[subset]
        y_subset = spend[subset]
        model0 = RandomForestRegressor(
            n_estimators=80,
            max_depth=6,
            min_samples_leaf=60,
            random_state=710 + index,
            n_jobs=1,
        ).fit(x_subset[~assigned], y_subset[~assigned])
        model1 = RandomForestRegressor(
            n_estimators=80,
            max_depth=6,
            min_samples_leaf=60,
            random_state=720 + index,
            n_jobs=1,
        ).fit(x_subset[assigned], y_subset[assigned])
        arm_models[arm] = (model0, model1)
    test_index = np.flatnonzero(test)
    effects = np.column_stack(
        [
            np.zeros(len(test_index)),
            arm_models[MENS][1].predict(x[test]) - arm_models[MENS][0].predict(x[test]),
            arm_models[WOMENS][1].predict(x[test]) - arm_models[WOMENS][0].predict(x[test]),
        ]
    )
    choices = np.argmax(effects, axis=1)
    arms = np.asarray([CONTROL, MENS, WOMENS])
    chosen = arms[choices]
    propensities = {
        arm: float(np.mean(treatment_text[train] == arm)) for arm in (CONTROL, MENS, WOMENS)
    }
    observed_arm = treatment_text[test]
    weights = np.asarray(
        [1 / propensities[arm] if chosen[i] == arm else 0.0 for i, arm in enumerate(observed_arm)]
    )
    personalized_value = float(np.mean(spend[test] * weights))
    segment_choice = np.where(
        frame["mens"].to_numpy()[test] == 1,
        MENS,
        np.where(frame["womens"].to_numpy()[test] == 1, WOMENS, best_static),
    )
    segment_weights = np.asarray(
        [
            1 / propensities[arm] if segment_choice[i] == arm else 0.0
            for i, arm in enumerate(observed_arm)
        ]
    )
    segment_value = float(np.mean(spend[test] * segment_weights))
    selected_rate = float(np.mean(chosen != CONTROL))
    scenario_cost = 0.50
    return {
        "rows": len(frame),
        "assignment": "RANDOMIZED_MULTI_ARM",
        "authority": "REAL_RANDOMIZED_REVENUE",
        "arm_results": arm_results,
        "development_means": development_means,
        "best_static": best_static,
        "test_control_spend": control_test,
        "test_best_static_spend": static_test,
        "personalized_spend_value": personalized_value,
        "personalized_minus_best_static": personalized_value - static_test,
        "predefined_segment_spend_value": segment_value,
        "segment_minus_best_static": segment_value - static_test,
        "scenario_contact_cost": scenario_cost,
        "personalized_scenario_net_value": personalized_value - scenario_cost * selected_rate,
        "profit_claim_permitted": False,
    }


def _criteo_model(x: np.ndarray, treatment: np.ndarray, outcome: np.ndarray) -> tuple[Any, Any]:
    parameters = {
        "max_iter": 70,
        "max_leaf_nodes": 15,
        "learning_rate": 0.08,
        "min_samples_leaf": 100,
        "random_state": 8271,
    }
    model0 = HistGradientBoostingRegressor(**parameters).fit(x[~treatment], outcome[~treatment])
    model1 = HistGradientBoostingRegressor(**parameters).fit(x[treatment], outcome[treatment])
    return model0, model1


def run_criteo() -> dict[str, object]:
    raw = REPOSITORY / "data/raw/criteo/criteo-research-uplift-v2.1.csv.gz"
    parquet = REPOSITORY / "data/processed/criteo/criteo-uplift-v2.1.parquet"
    adapter = CriteoUpliftAdapter(raw)
    profile = adapter.validate()
    sample = (
        pl.scan_parquet(parquet)
        .filter((pl.col("row_id").hash(seed=202608271) % 14) == 0)
        .collect()
    )
    row_bytes = sample["row_id"].to_numpy().tobytes()
    sample_hash = hashlib.sha256(row_bytes).hexdigest()
    split = sample["row_id"].hash(seed=202608272).to_numpy() % 10
    train = split < 6
    test = split >= 8
    feature_names = [f"f{index}" for index in range(12)]
    assert "exposure" not in feature_names
    x = sample.select(feature_names).to_numpy()
    treatment = sample["treatment"].to_numpy().astype(bool)
    outcomes: dict[str, object] = {}
    for outcome_name in ("conversion", "visit"):
        y = sample[outcome_name].to_numpy().astype(float)
        ate = _difference(y[test], treatment[test])
        model0, model1 = _criteo_model(x[train], treatment[train], y[train])
        prediction = model1.predict(x[test]) - model0.predict(x[test])
        policy = prediction > 0
        p = float(np.mean(treatment[train]))
        influence = treatment[test] * y[test] / p - (~treatment[test]) * y[test] / (1 - p)
        policy_value = float(np.mean(influence * policy))
        treat_all = float(np.mean(influence))
        bins = np.minimum(9, np.argsort(np.argsort(prediction)) * 10 // len(prediction))
        calibration = float(
            np.mean(
                [
                    abs(
                        float(np.mean(prediction[bins == decile]))
                        - float(np.mean(influence[bins == decile]))
                    )
                    for decile in range(10)
                ]
            )
        )
        rng = np.random.default_rng(991)
        shuffled = rng.permutation(treatment[test])
        shuffle_effect = float(np.mean(y[test][shuffled]) - np.mean(y[test][~shuffled]))
        outcomes[outcome_name] = {
            "ate": ate,
            "policy_value": policy_value,
            "treat_all_value": treat_all,
            "policy_minus_best_static": policy_value - max(0.0, treat_all),
            "treated_fraction": float(np.mean(policy)),
            "decile_calibration_mae": calibration,
            "shuffle_effect": shuffle_effect,
        }
    return {
        "full_rows_verified": profile["rows"],
        "official_hash_verified": profile["hash_matches_official"],
        "fixed_subsample_rows": len(sample),
        "fixed_subsample_row_id_sha256": sample_hash,
        "subsample_rule": "hash(row_id,202608271) mod 14 == 0",
        "assignment_column": "treatment",
        "exposure_forbidden": True,
        "authority": "REAL_RANDOMIZED_PROXY_OUTCOME",
        "outcomes": outcomes,
        "profit_claim_permitted": False,
    }


def _read_bandit_member(archive: Path, member: str) -> pl.DataFrame:
    with zipfile.ZipFile(archive) as source:
        data = source.read(member)
    return pl.read_csv(io.BytesIO(data), infer_schema_length=None)


def run_open_bandit() -> dict[str, object]:
    archive = REPOSITORY / "data/raw/open_bandit/zr-obp-master.zip"
    prefix = "zr-obp-master/obd"
    random = _read_bandit_member(archive, f"{prefix}/random/all/all.csv")
    bts = _read_bandit_member(archive, f"{prefix}/bts/all/all.csv")
    features = [
        "position",
        *[name for name in random.columns if name.startswith("user-item_affinity_")],
    ]
    random_x = random.select(features).to_numpy().astype(float)
    bts_x = bts.select(features).to_numpy().astype(float)
    random_y = random["click"].to_numpy().astype(float)
    bts_y = bts["click"].to_numpy().astype(float)
    reward_model = HistGradientBoostingRegressor(
        max_iter=60,
        max_leaf_nodes=15,
        min_samples_leaf=100,
        random_state=917,
    ).fit(random_x, random_y)
    random_prediction = reward_model.predict(random_x)
    bts_prediction = reward_model.predict(bts_x)
    target_propensity = 1 / 80
    behavior = bts["propensity_score"].to_numpy().astype(float)
    weights = target_propensity / behavior
    dm = float(np.mean(random_prediction))
    ips = float(np.mean(weights * bts_y))
    snips = float(np.sum(weights * bts_y) / np.sum(weights))
    dr = float(dm + np.mean(weights * (bts_y - bts_prediction)))
    switch = float(dm + np.mean(np.where(weights <= 10, weights * (bts_y - bts_prediction), 0)))
    ess = float(np.sum(weights) ** 2 / np.sum(weights**2))
    return {
        "random_rows": len(random),
        "bts_rows": len(bts),
        "local_release": "PUBLISHER_QUICK_SAMPLE_NOT_FULL_26M",
        "target_policy": "uniform_random_over_80_items",
        "random_ground_click_rate": float(np.mean(random_y)),
        "estimators": {"DM": dm, "IPS": ips, "SNIPS": snips, "DR": dr, "SwitchDR": switch},
        "effective_sample_size": ess,
        "ess_fraction": ess / len(bts),
        "max_weight": float(np.max(weights)),
        "unsupported_fraction": float(np.mean(~np.isfinite(weights) | (behavior <= 0))),
        "authority": "REAL_RANDOMIZED_PROXY_OUTCOME_CLICK",
        "commercial_value_claim_permitted": False,
    }


def run_x5() -> dict[str, object]:
    adapter = X5RetailHeroAdapter(REPOSITORY / "data/raw/x5_retailhero")
    provenance = adapter.audit()
    frame = adapter.materialize_features(
        REPOSITORY / "data/processed/x5_retailhero/v71_features.parquet"
    )
    numeric = [
        name
        for name, dtype in frame.schema.items()
        if name
        not in {
            "client_id",
            "treatment_flg",
            "target",
            "first_issue_date",
            "first_redeem_date",
            "gender",
        }
        and dtype.is_numeric()
    ]
    clean = frame.select("client_id", "treatment_flg", "target", *numeric).fill_null(0)
    bucket = clean["client_id"].hash(seed=712).to_numpy() % 10
    train = bucket < 7
    test = bucket >= 7
    x = clean.select(numeric).to_numpy().astype(float)
    treatment = clean["treatment_flg"].to_numpy().astype(bool)
    outcome = clean["target"].to_numpy().astype(float)
    model0 = RandomForestRegressor(
        n_estimators=80, max_depth=7, min_samples_leaf=80, random_state=712, n_jobs=1
    ).fit(x[train][~treatment[train]], outcome[train][~treatment[train]])
    model1 = RandomForestRegressor(
        n_estimators=80, max_depth=7, min_samples_leaf=80, random_state=713, n_jobs=1
    ).fit(x[train][treatment[train]], outcome[train][treatment[train]])
    score = model1.predict(x[test]) - model0.predict(x[test])
    observed = treatment[test] * outcome[test] / max(np.mean(treatment[test]), 1e-6) - (
        (~treatment[test]) * outcome[test] / max(np.mean(~treatment[test]), 1e-6)
    )
    top = score >= np.quantile(score, 0.8)
    return {
        "rows": len(frame),
        "features": len(numeric),
        "assignment_provenance": "UNKNOWN_ASSIGNMENT",
        "random_assignment_proven": provenance.random_assignment_proven,
        "top_quintile_association": float(np.mean(observed[top])),
        "overall_association": float(np.mean(observed)),
        "authority": "OBSERVATIONAL_ASSOCIATION",
        "causal_claim_permitted": False,
        "profit_claim_permitted": False,
    }


def run_all() -> dict[str, object]:
    payload: dict[str, object] = {
        "hillstrom": run_hillstrom(),
        "criteo": run_criteo(),
        "open_bandit": run_open_bandit(),
        "x5": run_x5(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    REPORT.write_text(_markdown(payload))
    return payload


def _markdown(payload: dict[str, object]) -> str:
    hillstrom = cast(dict[str, Any], payload["hillstrom"])
    criteo = cast(dict[str, Any], payload["criteo"])
    bandit = cast(dict[str, Any], payload["open_bandit"])
    x5 = cast(dict[str, Any], payload["x5"])
    return f"""# V7.1 real-data capability report

## Hillstrom

All {hillstrom["rows"]:,} randomized rows were used. Best static: `{hillstrom["best_static"]}`.
Personalized-minus-best-static spend: {hillstrom["personalized_minus_best_static"]:.6f}; predefined
segment-minus-best-static: {hillstrom["segment_minus_best_static"]:.6f}. Spend is revenue.
The $0.50 contact-cost result is scenario-only; no contribution-profit claim is permitted.

## Criteo

The full {criteo["full_rows_verified"]:,}-row file and publisher checksum were verified. The frozen
hash subsample contained {criteo["fixed_subsample_rows"]:,} rows. `treatment` was ITT assignment;
`exposure` was excluded. Authority is visit/conversion proxy outcome, never profit.

## Open Bandit

Random/BTS rows: {bandit["random_rows"]:,}/{bandit["bts_rows"]:,}. DR uniform-policy click estimate:
{bandit["estimators"]["DR"]:.6f}; ESS {bandit["effective_sample_size"]:.1f}. The local publisher
archive is the 10k quick sample, not the full 26M release. Click authority only.

## X5

Rows/features: {x5["rows"]:,}/{x5["features"]}. Assignment remains `UNKNOWN_ASSIGNMENT`.
Results have observational-association authority only.

## Claim conclusion

No dataset in this run supports a real merchant contribution-profit claim.
"""


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2, sort_keys=True))
