import numpy as np

from commercial_twin.safe_policy import SafeDRPolicyLearner


def fixture(effect: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(44)
    x = rng.normal(size=(1200, 4))
    action = rng.integers(0, 2, len(x))
    propensity = np.full(len(x), 0.5)
    uplift = (1.2 + 2.0 * (x[:, 0] > 0)) if effect else np.zeros(len(x))
    outcome = x[:, 1] + action * uplift + rng.normal(0, 0.5, len(x))
    return x, action, outcome, propensity


def test_cross_fitted_safe_policy_promotes_real_value() -> None:
    model = SafeDRPolicyLearner(min_leaf=50, seed=9).fit(*fixture())
    assert model.diagnostics_ is not None
    assert model.diagnostics_.lower > 0
    assert model.diagnostics_.promoted


def test_null_policy_falls_back_to_control() -> None:
    x, action, outcome, propensity = fixture(False)
    model = SafeDRPolicyLearner(min_leaf=50, seed=9).fit(x, action, outcome, propensity)
    assert np.all(model.predict(x[:100]) == 0)


def test_propensity_clipping_is_visible() -> None:
    x, action, outcome, propensity = fixture()
    propensity[:10] = 0.001
    model = SafeDRPolicyLearner(min_leaf=50).fit(x, action, outcome, propensity)
    assert model.diagnostics_ is not None
    assert model.diagnostics_.clipped_fraction > 0
