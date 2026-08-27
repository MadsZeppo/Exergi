import numpy as np

from decision_engine.forecasting.ensemble import EnsembleStrategy, historical_model_weights


def test_weights_only_reflect_supplied_historical_window() -> None:
    losses = {"a": np.array([100.0, 1.0]), "b": np.array([1.0, 2.0])}
    recent = historical_model_weights(losses, recent_window=1)
    all_history = historical_model_weights(losses)
    assert recent["a"] > recent["b"]
    assert all_history["a"] < all_history["b"]


def test_single_best_has_unit_weight() -> None:
    weights = historical_model_weights(
        {"a": np.array([1.0]), "b": np.array([2.0])}, strategy=EnsembleStrategy.SINGLE_BEST
    )
    assert weights == {"a": 1.0, "b": 0.0}
