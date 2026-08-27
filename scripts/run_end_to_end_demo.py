"""Execute the synthetic Merchant Validation V1 acceptance flow."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from commercial_twin.merchant_validation.service import build_demo_service


def main() -> None:
    as_of = datetime(2026, 8, 1, tzinfo=UTC)
    service = build_demo_service(as_of=as_of)
    merchant_id = service.merchant_id
    health = service.data_health(merchant_id, as_of=as_of)
    twins = service.build_twins(merchant_id, as_of=as_of)
    capability = service.capability_matrix(merchant_id, as_of=as_of)
    population = service.population_state(merchant_id, as_of=as_of)
    opportunities = service.discover_opportunities(merchant_id, as_of=as_of)
    if not opportunities:
        raise RuntimeError("demo truth-known opportunity was not discovered")
    card = service.decision_card(merchant_id, opportunities[0].id)
    experiment = service.create_experiment(merchant_id, opportunities[0].id)
    frozen = service.freeze_experiment(merchant_id, experiment.id, at=as_of)
    assignments = service.assign(merchant_id, experiment.id, at=as_of)
    outcomes = service.reveal_demo_outcomes(merchant_id, experiment.id)
    results = service.analyze(merchant_id, experiment.id)
    artifact = {
        "label": "SYNTHETIC DEMO — NOT COMMERCIAL EVIDENCE",
        "status": "PASS",
        "merchant_id": str(merchant_id),
        "data_health": health.model_dump(mode="json"),
        "customer_twins": len(twins),
        "capability_matrix": capability.model_dump(mode="json"),
        "population": population.model_dump(mode="json"),
        "opportunities": [item.model_dump(mode="json") for item in opportunities],
        "decision": card.model_dump(mode="json"),
        "experiment_spec_hash": frozen.spec_hash,
        "assignments": len(assignments),
        "outcomes": len(outcomes),
        "results": [item.model_dump(mode="json") for item in results],
        "ledger_records": len(service.ledger),
        "learning_records": len(service.learning_records),
    }
    path = Path("artifacts/merchant_validation_v1/demo_result.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "status": "PASS",
                "artifact": str(path),
                "customers": len(twins),
                "opportunities": len(opportunities),
                "assignments": len(assignments),
                "learning_records": len(service.learning_records),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
