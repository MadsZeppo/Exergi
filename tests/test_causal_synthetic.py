import numpy as np

from decision_engine.causal.synthetic import generate_confounded_treatment_data


def test_synthetic_dgp_has_known_heterogeneous_effect() -> None:
    data = generate_confounded_treatment_data(5000, seed=42)
    assert abs(data.true_effect.mean() - 5) < 0.1
    assert np.all((data.propensity > 0) & (data.propensity < 1))
