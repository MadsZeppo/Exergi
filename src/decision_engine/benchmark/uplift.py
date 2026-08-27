from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from decision_engine.causal.uplift import TLearnerUplift, uplift_curve_metrics
from decision_engine.datasets.hillstrom import CONTROL, MENS, HillstromDataset


def run_hillstrom_uplift(
    path: str | Path = "data/raw/hillstrom/hillstrom.csv",
    output_path: str | Path = "artifacts/world_state/hillstrom_uplift.json",
    seed: int = 42,
) -> dict[str, Any]:
    frame = HillstromDataset(path).load_rct()
    frame = frame.filter(frame["treatment"].is_in([CONTROL, MENS]))
    features = HillstromDataset.feature_columns(frame)
    categorical = [name for name in features if frame.schema[name] == pl.String]
    numeric = [name for name in features if name not in categorical]
    transformers: list[tuple[str, object, list[str]]] = []
    if numeric:
        transformers.append(("numeric", StandardScaler(), numeric))
    if categorical:
        transformers.append(
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical,
            )
        )
    preprocessor = Pipeline([("columns", ColumnTransformer(transformers))])
    x = frame.select(features).to_pandas()
    treatment = (frame["treatment"].to_numpy() == MENS).astype(int)
    outcome = frame["conversion"].to_numpy().astype(int)
    train, test = train_test_split(
        np.arange(frame.height), test_size=0.35, random_state=seed, stratify=treatment
    )
    x_train = preprocessor.fit_transform(x.iloc[train])
    x_test = preprocessor.transform(x.iloc[test])
    model = TLearnerUplift(seed=seed).fit(x_train, treatment[train], outcome[train])
    uplift = model.predict_uplift(x_test)
    metrics = uplift_curve_metrics(outcome[test], treatment[test], uplift)
    result = {
        "dataset": "Hillstrom randomized experiment",
        "question": "Mens email versus no email conversion uplift",
        "train_rows": len(train),
        "test_rows": len(test),
        "metrics": metrics,
        "interpretation": "ranking metric on randomized discrete treatment; not a discount model",
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
