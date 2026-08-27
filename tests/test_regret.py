from decision_engine.decision.regret import regret
from decision_engine.schemas import RegretType


def test_regret_requires_explicit_terminology() -> None:
    kind, value = regret(10, 7, RegretType.MODEL_ESTIMATED)
    assert kind == RegretType.MODEL_ESTIMATED
    assert value == 3
