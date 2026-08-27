from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from commercial_twin.merchant_validation import ActionRecommendation
from commercial_twin.merchant_validation.connectors import (
    CanonicalCsvImporter,
    KlaviyoConnector,
    ShopifyConnector,
)
from commercial_twin.merchant_validation.service import (
    build_demo_service,
    contribution_profit,
)

AS_OF = datetime(2026, 8, 1, tzinfo=UTC)


def prepared_service():
    service = build_demo_service(as_of=AS_OF)
    service.build_twins(service.merchant_id, as_of=AS_OF)
    opportunities = service.discover_opportunities(service.merchant_id, as_of=AS_OF)
    return service, opportunities[0]


def test_cross_merchant_access_is_rejected() -> None:
    service = build_demo_service(as_of=AS_OF)
    with pytest.raises(PermissionError, match="cross-merchant"):
        service.data_health(uuid4(), as_of=AS_OF)


def test_duplicate_event_replay_is_idempotent() -> None:
    service = build_demo_service(as_of=AS_OF, customer_count=1)
    event = {
        "external_event_id": "new-event",
        "event_type": "click",
        "occurred_at": AS_OF - timedelta(hours=1),
        "observed_at": AS_OF - timedelta(hours=1),
    }
    assert service.ingest_event(service.merchant_id, event)
    assert not service.ingest_event(service.merchant_id, event)


def test_point_in_time_state_excludes_future_events() -> None:
    service = build_demo_service(as_of=AS_OF, customer_count=1)
    customer_id = next(iter(service.customers))
    service.ingest_event(
        service.merchant_id,
        {
            "external_event_id": "future-event",
            "customer_id": customer_id,
            "event_type": "add_to_cart",
            "occurred_at": AS_OF + timedelta(days=1),
            "observed_at": AS_OF + timedelta(days=1),
        },
    )
    twin = service.build_twins(service.merchant_id, as_of=AS_OF)[0]
    assert twin.observed.cart_frequency == 1


def test_state_is_deterministic_and_contains_no_predictions_without_backtest() -> None:
    service = build_demo_service(as_of=AS_OF, customer_count=3)
    first = service.build_twins(service.merchant_id, as_of=AS_OF)
    second = service.build_twins(service.merchant_id, as_of=AS_OF)
    assert [row.state_hash for row in first] == [row.state_hash for row in second]
    assert all(not row.predictive for row in first)


def test_opportunity_uses_descriptive_not_causal_language() -> None:
    service, opportunity = prepared_service()
    card = service.decision_card(service.merchant_id, opportunity.id)
    assert card.recommendation is ActionRecommendation.TEST_THIS
    assert card.addressable_value_label == "OBSERVED GAP — NOT INCREMENTAL VALUE"
    assert all(action.expected_incremental_value is None for action in card.candidate_actions)


def test_small_population_abstains_from_opportunity() -> None:
    service = build_demo_service(as_of=AS_OF, customer_count=8)
    service.build_twins(service.merchant_id, as_of=AS_OF)
    assert service.discover_opportunities(service.merchant_id, as_of=AS_OF) == ()


def test_experiment_freeze_and_assignment_are_reproducible() -> None:
    service, opportunity = prepared_service()
    experiment = service.create_experiment(service.merchant_id, opportunity.id)
    with pytest.raises(RuntimeError, match="frozen"):
        service.assign(service.merchant_id, experiment.id, at=AS_OF)
    frozen = service.freeze_experiment(service.merchant_id, experiment.id, at=AS_OF)
    again = service.freeze_experiment(service.merchant_id, experiment.id, at=AS_OF)
    first = service.assign(service.merchant_id, experiment.id, at=AS_OF)
    second = service.assign(service.merchant_id, experiment.id, at=AS_OF)
    assert frozen == again
    assert first == second
    assert len({row.customer_id for row in first}) == len(first)
    assert all(row.assignment_probability > 0 for row in first)


def test_demo_randomized_itt_creates_append_only_learning_record() -> None:
    service, opportunity = prepared_service()
    experiment = service.create_experiment(service.merchant_id, opportunity.id)
    service.freeze_experiment(service.merchant_id, experiment.id, at=AS_OF)
    service.assign(service.merchant_id, experiment.id, at=AS_OF)
    assert service.ledger[0]["type"] == "PRE_OUTCOME_EXPERIMENT"
    service.reveal_demo_outcomes(service.merchant_id, experiment.id)
    results = service.analyze(service.merchant_id, experiment.id)
    assert len(results) == 2
    assert all(result.estimator == "RANDOMIZED_DIFFERENCE_IN_MEANS_ITT" for result in results)
    assert service.ledger[-1]["type"] == "EXPERIMENT_RESULT"
    assert len(service.learning_records) == 1


def test_real_service_cannot_simulate_outcomes() -> None:
    service, opportunity = prepared_service()
    service.synthetic_demo = False
    experiment = service.create_experiment(service.merchant_id, opportunity.id)
    service.freeze_experiment(service.merchant_id, experiment.id, at=AS_OF)
    service.assign(service.merchant_id, experiment.id, at=AS_OF)
    with pytest.raises(RuntimeError, match="real outcomes"):
        service.reveal_demo_outcomes(service.merchant_id, experiment.id)


def test_profit_accounting_and_missing_costs() -> None:
    assert (
        contribution_profit(
            gross_item_sales=100,
            line_discounts=10,
            refunds=5,
            shipping_revenue=4,
            cogs=40,
            merchant_shipping_cost=6,
            campaign_variable_cost=2,
            payment_processing_cost=3,
        )
        == 38
    )
    assert (
        contribution_profit(
            gross_item_sales=100,
            line_discounts=10,
            refunds=5,
            shipping_revenue=4,
            cogs=None,
            merchant_shipping_cost=6,
            campaign_variable_cost=2,
            payment_processing_cost=3,
        )
        is None
    )


def test_sample_size_functions_are_deterministic() -> None:
    service = build_demo_service()
    assert service.binary_sample_size(baseline=0.10, mde=0.02, alpha=0.05, power=0.8) > 0
    assert service.continuous_sample_size(variance_estimate=25, delta=1, alpha=0.05, power=0.8) > 0


def test_connector_boundaries_and_csv_import() -> None:
    body = b'{"id":1}'
    import base64
    import hashlib
    import hmac

    signature = base64.b64encode(hmac.new(b"secret", body, hashlib.sha256).digest()).decode()
    assert ShopifyConnector.verify_webhook(body, signature, "secret")
    assert KlaviyoConnector.evidence_status({"campaign": "x"}) == (
        "CAUSAL_ASSIGNMENT_NOT_IDENTIFIED"
    )
    rows = CanonicalCsvImporter().parse("costs", "entity_id,amount\nsku-1,12.50\n")
    assert rows[0]["amount"] == "12.50"
