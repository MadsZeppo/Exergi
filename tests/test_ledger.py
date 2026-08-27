from datetime import UTC, datetime

import duckdb
import pytest

from decision_engine.ledger.store import PredictionLedger
from decision_engine.schemas import (
    ActionOutcomeDistribution,
    DecisionPrediction,
    EvidenceLevel,
    EvidenceStatus,
)


def prediction() -> DecisionPrediction:
    evidence = EvidenceStatus(overall=EvidenceLevel.HIGH)
    distribution = ActionOutcomeDistribution(
        action_id="none",
        expected_value=1,
        p05=0,
        p10=0,
        p25=0.5,
        p50=1,
        p75=1.5,
        p90=2,
        p95=2,
        std=0.5,
        probability_positive=0.9,
        probability_beat_baseline=0.5,
        evidence_status=evidence,
    )
    now = datetime.now(UTC)
    return DecisionPrediction(
        decision_id="d1",
        model_version="v1",
        created_at=now,
        data_cutoff=now,
        action_distributions=(distribution,),
        recommended_action="none",
    )


def test_ledger_rejects_prediction_mutation(tmp_path) -> None:
    ledger = PredictionLedger(tmp_path / "ledger.duckdb")
    kwargs = dict(
        dataset_name="test",
        dataset_version="1",
        model_name="baseline",
        config={},
        random_seed=42,
        state_snapshot={},
    )
    ledger.append_prediction(prediction(), prediction_id="fixed", **kwargs)
    with pytest.raises(duckdb.ConstraintException):
        ledger.append_prediction(prediction(), prediction_id="fixed", **kwargs)
    ledger.close()
