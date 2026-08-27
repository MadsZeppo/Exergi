from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler


class ContinuousTreatmentEstimator(ABC):
    assumptions: tuple[str, ...]
    causal: bool = False

    @abstractmethod
    def fit(self, frame: pl.DataFrame, features: list[str]) -> ContinuousTreatmentEstimator: ...

    @abstractmethod
    def dose_response(self, frame: pl.DataFrame, doses: np.ndarray) -> np.ndarray: ...


@dataclass
class ContinuousOutcomeRegression(ContinuousTreatmentEstimator):
    kind: str = "flexible"
    seed: int = 42
    assumptions: tuple[str, ...] = (
        "conditional exchangeability if interpreted causally",
        "consistency",
        "positivity",
    )
    causal: bool = False

    def fit(self, frame: pl.DataFrame, features: list[str]) -> ContinuousOutcomeRegression:
        forbidden = {"observed_sales", "website_traffic_after_promo"} & set(features)
        if forbidden:
            raise ValueError(f"post-treatment outcomes cannot be controls: {sorted(forbidden)}")
        self.features_ = features
        x = frame.select(features + ["discount"]).to_pandas()
        categorical = [name for name in features if frame.schema[name] == pl.String]
        numeric = [name for name in features if name not in categorical] + ["discount"]
        preprocess = ColumnTransformer(
            [
                ("numeric", StandardScaler(), numeric),
                ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
            ]
        )
        if self.kind == "naive":
            x = frame.select("discount").to_pandas()
            preprocess = ColumnTransformer([("dose", PolynomialFeatures(3), ["discount"])])
            model: object = Ridge(alpha=1.0)
        elif self.kind == "elasticity":
            model = Ridge(alpha=10.0)
        else:
            model = HistGradientBoostingRegressor(
                max_iter=150, max_leaf_nodes=24, min_samples_leaf=30, random_state=self.seed
            )
        self.model_ = Pipeline([("preprocess", preprocess), ("model", model)])
        self.model_.fit(x, np.log1p(frame["observed_sales"].to_numpy()))
        return self

    def dose_response(self, frame: pl.DataFrame, doses: np.ndarray) -> np.ndarray:
        result: list[np.ndarray] = []
        for dose in np.asarray(doses):
            if self.kind == "naive":
                x = pl.DataFrame({"discount": [float(dose)] * frame.height}).to_pandas()
            else:
                x = frame.select(self.features_).to_pandas()
                x["discount"] = float(dose)
            result.append(np.expm1(self.model_.predict(x)).clip(0))
        return np.column_stack(result)


@dataclass
class GaussianGeneralizedPropensity:
    seed: int = 42

    def fit(self, frame: pl.DataFrame, features: list[str]) -> GaussianGeneralizedPropensity:
        numeric = [name for name in features if frame.schema[name] != pl.String]
        self.features_ = numeric
        self.model_ = Ridge(alpha=5.0).fit(
            frame.select(numeric).to_numpy(), frame["discount"].to_numpy()
        )
        residual = frame["discount"].to_numpy() - self.model_.predict(
            frame.select(numeric).to_numpy()
        )
        self.sigma_ = max(float(np.std(residual)), 1e-3)
        return self

    def density(self, frame: pl.DataFrame, doses: np.ndarray) -> np.ndarray:
        mean = self.model_.predict(frame.select(self.features_).to_numpy())[:, None]
        z = (np.asarray(doses)[None, :] - mean) / self.sigma_
        return np.exp(-0.5 * z**2) / (self.sigma_ * np.sqrt(2 * np.pi))
