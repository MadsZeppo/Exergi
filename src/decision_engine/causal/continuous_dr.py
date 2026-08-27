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

from decision_engine.causal.continuous import ContinuousTreatmentEstimator

FORBIDDEN_CONTROLS = frozenset({"observed_sales", "website_traffic_after_promo", "price"})


def _validate_features(frame: pl.DataFrame, features: list[str]) -> None:
    forbidden = FORBIDDEN_CONTROLS & set(features)
    if forbidden:
        raise ValueError(f"post-treatment outcomes cannot be controls: {sorted(forbidden)}")
    missing = set(features) - set(frame.columns)
    if missing:
        raise ValueError(f"features missing from frame: {sorted(missing)}")


def _pipeline(
    frame: pl.DataFrame,
    features: list[str],
    *,
    flexible: bool,
    seed: int,
    include_dose: bool,
) -> Pipeline:
    columns = features + (["discount"] if include_dose else [])
    categorical = [name for name in columns if frame.schema[name] == pl.String]
    numeric = [name for name in columns if name not in categorical]
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
    preprocess = ColumnTransformer(transformers)
    model: object
    if flexible:
        model = HistGradientBoostingRegressor(
            max_iter=120,
            max_leaf_nodes=20,
            min_samples_leaf=25,
            l2_regularization=1.0,
            random_state=seed,
        )
    else:
        model = Ridge(alpha=5.0)
    return Pipeline([("preprocess", preprocess), ("model", model)])


@dataclass
class OutcomeNuisance:
    kind: str = "flexible"
    seed: int = 42

    def fit(self, frame: pl.DataFrame, features: list[str]) -> OutcomeNuisance:
        _validate_features(frame, features)
        if self.kind not in {"parametric", "flexible"}:
            raise ValueError("outcome nuisance must be parametric or flexible")
        self.features_ = list(features)
        if self.kind == "parametric":
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
            transformers.append(("dose", PolynomialFeatures(3, include_bias=False), ["discount"]))
            self.model_ = Pipeline(
                [("preprocess", ColumnTransformer(transformers)), ("model", Ridge(alpha=5.0))]
            )
        else:
            self.model_ = _pipeline(
                frame, features, flexible=True, seed=self.seed, include_dose=True
            )
        self.model_.fit(
            frame.select(features + ["discount"]).to_pandas(),
            frame["observed_sales"].to_numpy(),
        )
        return self

    def predict(self, frame: pl.DataFrame, doses: np.ndarray | float) -> np.ndarray:
        values = np.atleast_1d(np.asarray(doses, dtype=float))
        predictions: list[np.ndarray] = []
        for dose in values:
            x = frame.select(self.features_).to_pandas()
            x["discount"] = float(dose)
            predictions.append(np.maximum(self.model_.predict(x), 0.0))
        return np.column_stack(predictions)

    def predict_observed(self, frame: pl.DataFrame) -> np.ndarray:
        x = frame.select(self.features_ + ["discount"]).to_pandas()
        return np.maximum(self.model_.predict(x), 0.0)


class TreatmentDensityNuisance(ABC):
    @abstractmethod
    def fit(self, frame: pl.DataFrame, features: list[str]) -> TreatmentDensityNuisance: ...

    @abstractmethod
    def density(self, frame: pl.DataFrame, doses: np.ndarray) -> np.ndarray: ...

    def observed_density(self, frame: pl.DataFrame) -> np.ndarray:
        result = self.density(frame, frame["discount"].to_numpy())
        return np.diag(result)


@dataclass
class ConditionalTreatmentDensity(TreatmentDensityNuisance):
    kind: str = "kernel_residual"
    seed: int = 42
    residual_sample_size: int = 512

    def fit(self, frame: pl.DataFrame, features: list[str]) -> ConditionalTreatmentDensity:
        _validate_features(frame, features)
        if self.kind not in {"gaussian", "kernel_residual"}:
            raise ValueError("density nuisance must be gaussian or kernel_residual")
        self.features_ = list(features)
        self.model_ = _pipeline(
            frame,
            features,
            flexible=self.kind == "kernel_residual",
            seed=self.seed,
            include_dose=False,
        )
        x = frame.select(features).to_pandas()
        dose = frame["discount"].to_numpy()
        self.model_.fit(x, dose)
        residuals = dose - self.model_.predict(x)
        self.sigma_ = max(float(np.std(residuals, ddof=1)), 0.005)
        if residuals.size > self.residual_sample_size:
            rng = np.random.default_rng(self.seed)
            residuals = residuals[rng.choice(residuals.size, self.residual_sample_size, False)]
        self.residuals_ = np.asarray(residuals)
        iqr = float(np.subtract(*np.percentile(self.residuals_, [75, 25])))
        scale = min(self.sigma_, iqr / 1.34) if iqr > 0 else self.sigma_
        self.bandwidth_ = max(0.9 * scale * max(self.residuals_.size, 2) ** (-0.2), 0.004)
        return self

    def density(self, frame: pl.DataFrame, doses: np.ndarray) -> np.ndarray:
        mean = self.model_.predict(frame.select(self.features_).to_pandas())[:, None]
        candidates = np.asarray(doses, dtype=float)[None, :]
        if self.kind == "gaussian":
            z = (candidates - mean) / self.sigma_
            return np.exp(-0.5 * z**2) / (self.sigma_ * np.sqrt(2 * np.pi))
        target_residual = candidates - mean
        z = (target_residual[:, :, None] - self.residuals_[None, None, :]) / self.bandwidth_
        return np.mean(np.exp(-0.5 * z**2), axis=2) / (
            self.bandwidth_ * np.sqrt(2 * np.pi)
        )

    def observed_density(self, frame: pl.DataFrame) -> np.ndarray:
        mean = self.model_.predict(frame.select(self.features_).to_pandas())
        target = frame["discount"].to_numpy() - mean
        if self.kind == "gaussian":
            z = target / self.sigma_
            return np.exp(-0.5 * z**2) / (self.sigma_ * np.sqrt(2 * np.pi))
        z = (target[:, None] - self.residuals_[None, :]) / self.bandwidth_
        return np.mean(np.exp(-0.5 * z**2), axis=1) / (
            self.bandwidth_ * np.sqrt(2 * np.pi)
        )


@dataclass(frozen=True)
class DensityDiagnostics:
    floor: float
    fraction_clipped: float
    minimum_effective_density: float
    median_effective_density: float
    maximum_effective_density: float
    effective_sample_size: float
    maximum_inverse_weight: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CrossFitFold:
    fold: int
    train_rows: tuple[int, ...]
    validation_rows: tuple[int, ...]
    train_max_date: str
    validation_min_date: str


@dataclass
class ContinuousDRDoseResponseEstimator(ContinuousTreatmentEstimator):
    outcome_kind: str = "flexible"
    density_kind: str = "kernel_residual"
    n_splits: int = 3
    bandwidth: float = 0.025
    density_floor: float = 0.05
    seed: int = 42
    assumptions: tuple[str, ...] = (
        "consistency",
        "conditional exchangeability given declared pre-treatment features",
        "conditional positivity in the reported support region",
        "no interference for the single-treatment estimand",
    )
    causal: bool = True

    def fit(
        self, frame: pl.DataFrame, features: list[str]
    ) -> ContinuousDRDoseResponseEstimator:
        _validate_features(frame, features)
        if "date" not in frame.columns:
            raise ValueError("strict chronological cross-fitting requires a date column")
        if self.n_splits < 2:
            raise ValueError("n_splits must be at least two")
        ordered = frame.with_row_index("__original_row").sort("date")
        dates = ordered["date"].unique(maintain_order=True).to_list()
        blocks = [
            block.tolist()
            for block in np.array_split(np.arange(len(dates)), self.n_splits + 1)
        ]
        observed = ordered["observed_sales"].to_numpy()
        dose = ordered["discount"].to_numpy()
        m_observed = np.full(ordered.height, np.nan)
        f_observed = np.full(ordered.height, np.nan)
        validation_mask = np.zeros(ordered.height, dtype=bool)
        folds: list[CrossFitFold] = []
        for fold in range(self.n_splits):
            train_dates = [dates[index] for part in blocks[: fold + 1] for index in part]
            validation_dates = [dates[index] for index in blocks[fold + 1]]
            if not train_dates or not validation_dates:
                continue
            train_idx = np.flatnonzero(ordered["date"].is_in(train_dates).to_numpy())
            valid_idx = np.flatnonzero(ordered["date"].is_in(validation_dates).to_numpy())
            train = ordered[train_idx]
            valid = ordered[valid_idx]
            outcome_model = OutcomeNuisance(self.outcome_kind, self.seed + fold).fit(
                train, features
            )
            density_model = ConditionalTreatmentDensity(
                self.density_kind, self.seed + fold
            ).fit(train, features)
            m_observed[valid_idx] = outcome_model.predict_observed(valid)
            f_observed[valid_idx] = density_model.observed_density(valid)
            validation_mask[valid_idx] = True
            folds.append(
                CrossFitFold(
                    fold,
                    tuple(map(int, train["__original_row"].to_list())),
                    tuple(map(int, valid["__original_row"].to_list())),
                    str(max(train_dates)),
                    str(min(validation_dates)),
                )
            )
        if not validation_mask.any():
            raise ValueError("not enough dates for chronological cross-fitting")
        raw_density = f_observed[validation_mask]
        effective_density = np.maximum(raw_density, self.density_floor)
        inverse = 1.0 / effective_density
        ess = float(inverse.sum() ** 2 / np.sum(inverse**2))
        fraction_clipped = float(np.mean(raw_density < self.density_floor))
        warnings: list[str] = []
        if fraction_clipped > 0.05:
            warnings.append("more than 5% of cross-fitted treatment densities were clipped")
        if ess < 0.25 * effective_density.size:
            warnings.append("inverse-density effective sample size is below 25%")
        self.density_diagnostics_ = DensityDiagnostics(
            self.density_floor,
            fraction_clipped,
            float(effective_density.min()),
            float(np.median(effective_density)),
            float(effective_density.max()),
            ess,
            float(inverse.max()),
            tuple(warnings),
        )
        self.features_ = list(features)
        self.crossfit_folds_ = tuple(folds)
        self.crossfit_frame_ = ordered.filter(pl.Series(validation_mask)).drop("__original_row")
        self.crossfit_dose_ = dose[validation_mask]
        self.crossfit_residual_ = observed[validation_mask] - m_observed[validation_mask]
        self.crossfit_density_ = effective_density
        self.outcome_model_ = OutcomeNuisance(self.outcome_kind, self.seed).fit(ordered, features)
        self.density_model_ = ConditionalTreatmentDensity(
            self.density_kind, self.seed
        ).fit(ordered, features)
        return self

    def dose_response(self, frame: pl.DataFrame, doses: np.ndarray) -> np.ndarray:
        candidates = np.asarray(doses, dtype=float)
        plug_in = self.outcome_model_.predict(frame, candidates)
        corrections = np.zeros(candidates.size)
        for index, dose in enumerate(candidates):
            kernel = np.exp(-0.5 * ((self.crossfit_dose_ - dose) / self.bandwidth) ** 2)
            kernel /= self.bandwidth * np.sqrt(2 * np.pi)
            weights = kernel / self.crossfit_density_
            corrections[index] = (
                float(np.sum(weights * self.crossfit_residual_) / np.sum(weights))
                if np.sum(weights) > 1e-10
                else 0.0
            )
        self.last_corrections_ = corrections
        return np.maximum(plug_in + corrections[None, :], 0.0)

    def conditional_density(self, frame: pl.DataFrame, doses: np.ndarray) -> np.ndarray:
        return self.density_model_.density(frame, np.asarray(doses, dtype=float))
