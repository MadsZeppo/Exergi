from __future__ import annotations

import numpy as np

from decision_engine.causal.challengers import (
    DoWhyValidator,
    EconMLContinuousDMLChallenger,
)


def test_optional_dowhy_fails_closed_when_unavailable() -> None:
    validator = DoWhyValidator()
    if not validator.available():
        result = validator.validate_binary(
            {"treatment": [0, 1], "outcome": [0, 1], "x": [0.0, 1.0]},
            treatment="treatment",
            outcome="outcome",
            common_causes=["x"],
        )
        assert result.status == "NOT_INSTALLED"
        assert not result.available


def test_optional_econml_fails_closed_when_unavailable() -> None:
    challenger = EconMLContinuousDMLChallenger()
    if not challenger.available():
        result = challenger.fit_effect(
            np.ones((4, 1)), np.arange(4, dtype=float), np.arange(4, dtype=float)
        )
        assert result.status == "NOT_INSTALLED"
        assert not result.available
