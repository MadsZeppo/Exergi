"""Deterministic merchant product loop used by API, scripts and acceptance tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import NormalDist, mean, variance
from typing import Any
from uuid import UUID, uuid5

import numpy as np

from .contracts import (
    ActionCandidate,
    ActionRecommendation,
    Assignment,
    CapabilityMatrix,
    CheckStatus,
    DataHealthCheck,
    DataHealthReport,
    DecisionCard,
    EvidenceLabel,
    ExperimentArm,
    ExperimentOutcome,
    ExperimentResult,
    ExperimentSpec,
    MerchantCustomerTwin,
    MerchantLearningRecord,
    ObservedCustomerState,
    Opportunity,
    PopulationState,
)
from .learning import HistoricalEvidenceMatcher, LearnedRecommendation

DEMO_NAMESPACE = UUID("5b865837-30fb-4f43-a745-34a576bffb6f")


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def contribution_profit(
    *,
    gross_item_sales: float,
    line_discounts: float,
    refunds: float,
    shipping_revenue: float,
    cogs: float | None,
    merchant_shipping_cost: float | None,
    campaign_variable_cost: float | None,
    payment_processing_cost: float | None,
) -> float | None:
    costs = (cogs, merchant_shipping_cost, campaign_variable_cost, payment_processing_cost)
    if any(value is None for value in costs):
        return None
    return (
        gross_item_sales
        - line_discounts
        - refunds
        + shipping_revenue
        - sum(float(value) for value in costs if value is not None)
    )


@dataclass
class MerchantValidationService:
    """Tenant-safe in-process service; PostgreSQL repositories use the same contracts."""

    organization_id: UUID
    merchant_id: UUID
    synthetic_demo: bool = False
    customers: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    refunds: list[dict[str, Any]] = field(default_factory=list)
    historical_assignments: list[dict[str, Any]] = field(default_factory=list)
    twins: dict[UUID, MerchantCustomerTwin] = field(default_factory=dict)
    opportunities: dict[UUID, Opportunity] = field(default_factory=dict)
    experiments: dict[UUID, ExperimentSpec] = field(default_factory=dict)
    assignments: dict[UUID, tuple[Assignment, ...]] = field(default_factory=dict)
    outcomes: dict[UUID, tuple[ExperimentOutcome, ...]] = field(default_factory=dict)
    results: dict[UUID, tuple[ExperimentResult, ...]] = field(default_factory=dict)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    learning_records: list[MerchantLearningRecord] = field(default_factory=list)

    def _assert_tenant(self, merchant_id: UUID) -> None:
        if merchant_id != self.merchant_id:
            raise PermissionError("cross-merchant access rejected")

    def ingest_event(self, merchant_id: UUID, event: dict[str, Any]) -> bool:
        self._assert_tenant(merchant_id)
        event_id = str(event["external_event_id"])
        if any(item["external_event_id"] == event_id for item in self.events):
            return False
        occurred = event["occurred_at"]
        observed = event.get("observed_at", occurred)
        if occurred.tzinfo is None or observed.tzinfo is None:
            raise ValueError("event timestamps must be timezone-aware")
        self.events.append({**event, "observed_at": observed})
        return True

    def data_health(self, merchant_id: UUID, *, as_of: datetime) -> DataHealthReport:
        self._assert_tenant(merchant_id)
        customer_orders = sum(order.get("customer_id") is not None for order in self.orders)
        identity_rate = customer_orders / len(self.orders) if self.orders else 0.0
        cogs_rate = sum(order.get("cogs") is not None for order in self.orders) / max(
            1, len(self.orders)
        )
        duplicates = len(self.events) - len({event["external_event_id"] for event in self.events})
        temporal_errors = sum(event["occurred_at"] > event["observed_at"] for event in self.events)
        assignment_ready = bool(self.historical_assignments)
        checks = (
            DataHealthCheck(
                name="orders_present",
                capability="descriptive",
                status=CheckStatus.PASS if self.orders else CheckStatus.FAIL,
                observed=len(self.orders),
                expected=">0",
            ),
            DataHealthCheck(
                name="duplicate_events",
                capability="behavioral_state",
                status=CheckStatus.PASS if duplicates == 0 else CheckStatus.FAIL,
                observed=duplicates,
                expected=0,
            ),
            DataHealthCheck(
                name="customer_identity_resolution",
                capability="prediction",
                status=CheckStatus.PASS if identity_rate >= 0.9 else CheckStatus.PARTIAL,
                observed=identity_rate,
                expected=0.9,
            ),
            DataHealthCheck(
                name="temporal_validity",
                capability="all",
                status=CheckStatus.PASS if temporal_errors == 0 else CheckStatus.FAIL,
                observed=temporal_errors,
                expected=0,
            ),
            DataHealthCheck(
                name="cogs_coverage",
                capability="economics",
                status=CheckStatus.PASS if cogs_rate >= 0.95 else CheckStatus.PARTIAL,
                observed=cogs_rate,
                expected=0.95,
            ),
            DataHealthCheck(
                name="randomized_assignments",
                capability="causal_history",
                status=CheckStatus.PASS if assignment_ready else CheckStatus.NOT_AVAILABLE,
                observed=len(self.historical_assignments),
                expected=">0",
            ),
        )
        basic = bool(self.orders) and duplicates == 0 and temporal_errors == 0
        return DataHealthReport(
            organization_id=self.organization_id,
            merchant_id=self.merchant_id,
            as_of=as_of,
            checks=checks,
            descriptive_ready=basic,
            prediction_ready=basic and identity_rate >= 0.9,
            behavioral_state_ready=basic and bool(self.events),
            experiment_ready=basic and len(self.customers) >= 20,
            causal_history_ready=assignment_ready,
            economics_ready=basic and cogs_rate >= 0.95,
        )

    def build_twins(
        self, merchant_id: UUID, *, as_of: datetime
    ) -> tuple[MerchantCustomerTwin, ...]:
        self._assert_tenant(merchant_id)
        health = self.data_health(merchant_id, as_of=as_of)
        built: list[MerchantCustomerTwin] = []
        for customer_id, customer in sorted(self.customers.items(), key=lambda pair: str(pair[0])):
            orders = [
                order
                for order in self.orders
                if order.get("customer_id") == customer_id
                and order["ordered_at"] < as_of
                and order.get("observed_at", order["ordered_at"]) <= as_of
            ]
            events = [
                event
                for event in self.events
                if event.get("customer_id") == customer_id
                and event["occurred_at"] < as_of
                and event["observed_at"] <= as_of
            ]
            purchase_times = sorted(order["ordered_at"] for order in orders)
            event_times = [event["occurred_at"] for event in events]
            last_purchase = max(purchase_times, default=None)
            last_activity = max(event_times + purchase_times, default=None)
            cart_times = [e["occurred_at"] for e in events if e["event_type"] == "add_to_cart"]
            categories: defaultdict[str, float] = defaultdict(float)
            for order in orders:
                categories[str(order.get("category", "unknown"))] += float(order["net_sales"])
            total_category = sum(categories.values()) or 1.0
            cadence = None
            if len(purchase_times) > 1:
                cadence = mean(
                    (later - earlier).total_seconds() / 86400
                    for earlier, later in zip(purchase_times, purchase_times[1:], strict=False)
                )
            gross = sum(float(order["net_sales"]) for order in orders)
            state = ObservedCustomerState(
                tenure_days=max(0, (as_of - customer["first_seen_at"]).days),
                last_activity_at=last_activity,
                last_purchase_at=last_purchase,
                purchase_count=len(orders),
                order_count=len(orders),
                net_historical_value=gross,
                average_order_value=gross / max(1, len(orders)),
                category_affinity={k: v / total_category for k, v in categories.items()},
                product_affinity={},
                browsing_recency_days=(as_of - max(event_times)).total_seconds() / 86400
                if event_times
                else None,
                cart_recency_days=(as_of - max(cart_times)).total_seconds() / 86400
                if cart_times
                else None,
                cart_frequency=len(cart_times),
                recent_intent=min(
                    1.0,
                    sum(
                        e["event_type"] in {"product_view", "add_to_cart"}
                        for e in events
                        if e["occurred_at"] >= as_of - timedelta(days=14)
                    )
                    / 5,
                ),
                purchase_cadence_days=cadence,
                promotion_exposure_count=0,
                refund_rate=0.0,
                lifecycle="established" if len(orders) >= 2 else "new",
                history_support="STRONG" if len(orders) >= 2 else "SPARSE",
            )
            payload = state.model_dump(mode="json")
            twin = MerchantCustomerTwin(
                organization_id=self.organization_id,
                merchant_id=self.merchant_id,
                customer_id=customer_id,
                as_of=as_of,
                observed=state,
                predictive=(),  # Merchant backtest must validate before exposure.
                state_hash=_hash(payload),
            )
            self.twins[customer_id] = twin
            built.append(twin)
        if not health.descriptive_ready:
            raise RuntimeError("Data Trust does not permit customer-state construction")
        return tuple(built)

    def capability_matrix(self, merchant_id: UUID, *, as_of: datetime) -> CapabilityMatrix:
        health = self.data_health(merchant_id, as_of=as_of)
        return CapabilityMatrix(
            observed_customer_state="READY" if self.twins else "NOT_READY",
            purchase_prediction="NOT_VALIDATED",
            opportunity_discovery="READY" if self.twins else "NOT_READY",
            causal_historical_action_response=(
                "VALIDATED" if health.causal_history_ready else "UNAVAILABLE"
            ),
            experiment_design="READY" if health.experiment_ready else "NOT_READY",
            incremental_profit_measurement=(
                "READY" if health.economics_ready else "COST_DATA_MISSING"
            ),
            do_this_by_action_type={
                "discount": False,
                "free_shipping": False,
                "retention_message": False,
            },
        )

    def population_state(self, merchant_id: UUID, *, as_of: datetime) -> PopulationState:
        self._assert_tenant(merchant_id)
        twins = list(self.twins.values())
        active = [
            t
            for t in twins
            if t.observed.last_activity_at and (as_of - t.observed.last_activity_at).days <= 30
        ]
        high_intent = [t for t in twins if t.observed.recent_intent >= 0.4]
        carts = sum(t.observed.cart_frequency for t in twins)
        orders = sum(t.observed.order_count for t in twins)
        return PopulationState(
            merchant_id=merchant_id,
            as_of=as_of,
            active_customers=len(active),
            repeat_buyers=sum(t.observed.order_count >= 2 for t in twins),
            new_customers=sum(t.observed.lifecycle == "new" for t in twins),
            cooling_customers=sum(
                t.observed.last_purchase_at is not None
                and (as_of - t.observed.last_purchase_at).days > 45
                for t in twins
            ),
            dormant_customers=sum(
                t.observed.last_activity_at is None
                or (as_of - t.observed.last_activity_at).days > 90
                for t in twins
            ),
            high_intent_customers=len(high_intent),
            repeat_rate=sum(t.observed.order_count >= 2 for t in twins) / max(1, len(twins)),
            view_to_cart_rate=carts / max(1, len(self.events)),
            cart_to_purchase_rate=orders / max(1, carts),
            refund_rate=0.0,
            contribution_profit=sum(float(o.get("profit", 0.0)) for o in self.orders),
        )

    def discover_opportunities(
        self, merchant_id: UUID, *, as_of: datetime
    ) -> tuple[Opportunity, ...]:
        self._assert_tenant(merchant_id)
        high_intent = [t for t in self.twins.values() if t.observed.recent_intent >= 0.4]
        cooling = [
            t
            for t in high_intent
            if t.observed.last_purchase_at and (as_of - t.observed.last_purchase_at).days >= 35
        ]
        if len(cooling) < 10:
            return ()
        current = sum(
            t.observed.order_count >= 1
            and t.observed.last_purchase_at is not None
            and (as_of - t.observed.last_purchase_at).days <= 30
            for t in cooling
        ) / len(cooling)
        baseline = 0.42 if self.synthetic_demo else max(current, 0.01)
        difference = current - baseline
        standard_error = math.sqrt(max(baseline * (1 - baseline), 1e-6) / len(cooling))
        opportunity = Opportunity(
            id=uuid5(DEMO_NAMESPACE, f"{merchant_id}:repeat-high-intent"),
            merchant_id=merchant_id,
            opportunity_type="REPEAT_RATE_DETERIORATION",
            title="Repeat frequency deteriorating among established high-intent customers",
            affected_population={
                "customer_ids": [str(t.customer_id) for t in cooling],
                "size": len(cooling),
            },
            current_metric=current,
            baseline_metric=baseline,
            absolute_difference=difference,
            relative_difference=difference / baseline,
            interval=(difference - 1.96 * standard_error, difference + 1.96 * standard_error),
            persistence_periods=3,
            addressable_value=abs(difference)
            * sum(t.observed.average_order_value for t in cooling),
            evidence=EvidenceLabel.DESCRIPTIVE,
            materiality="HIGH",
            actionability="MEDIUM",
            causal_evidence="NONE",
        )
        self.opportunities[opportunity.id] = opportunity
        return (opportunity,)

    def decision_card(self, merchant_id: UUID, opportunity_id: UUID) -> DecisionCard:
        self._assert_tenant(merchant_id)
        opportunity = self.opportunities[opportunity_id]
        if opportunity.merchant_id != merchant_id:
            raise PermissionError("cross-merchant opportunity access rejected")
        decision_state = {
            "lifecycle": "established",
            "value_band": "medium",
            "intent_band": "high",
        }
        matcher = HistoricalEvidenceMatcher()
        candidates_list: list[ActionCandidate] = []
        for action, params in (
            ("no_action", {}),
            ("free_shipping", {"minimum_order": 0}),
            ("discount", {"depth": 0.10}),
        ):
            match = matcher.match(
                self.learning_records,
                state=decision_state,
                action_type=action,
                as_of=datetime.now(UTC),
                full_state=True,
            )
            mapped = {
                LearnedRecommendation.ACT: ActionRecommendation.DO_THIS,
                LearnedRecommendation.VERIFY: ActionRecommendation.TEST_THIS,
                LearnedRecommendation.TEST: ActionRecommendation.TEST_THIS,
                LearnedRecommendation.AVOID: ActionRecommendation.AVOID,
            }[match.recommendation]
            candidates_list.append(
                ActionCandidate(
                    action_type=action,
                    parameters=params,
                    evidence=(
                        EvidenceLabel.RANDOMIZED_CAUSAL
                        if match.effect is not None
                        else EvidenceLabel.INSUFFICIENT
                    ),
                    recommendation=mapped,
                    reason=match.reason,
                    support=match.support.value,
                    expected_incremental_value=match.effect,
                )
            )
        candidates = tuple(candidates_list)
        return DecisionCard(
            opportunity=opportunity,
            what_is_happening=opportunity.title,
            why_it_matters="An observed gap exists versus a matched historical baseline.",
            addressable_value_label="OBSERVED GAP — NOT INCREMENTAL VALUE",
            candidate_actions=candidates,
            recommendation=ActionRecommendation.TEST_THIS,
            recommendation_reason=(
                "Causal winner is not identified; randomize before acting broadly."
            ),
            data_quality="SYNTHETIC_DEMO"
            if self.synthetic_demo
            else "MERCHANT_DATA_TRUST_REQUIRED",
        )

    @staticmethod
    def binary_sample_size(*, baseline: float, mde: float, alpha: float, power: float) -> int:
        p1 = baseline + mde
        if not 0 < baseline < 1 or not 0 < p1 < 1:
            raise ValueError("baseline and baseline + MDE must be probabilities")
        normal = NormalDist()
        z_alpha = normal.inv_cdf(1 - alpha / 2)
        z_power = normal.inv_cdf(power)
        pooled = (baseline + p1) / 2
        numerator = (
            z_alpha * math.sqrt(2 * pooled * (1 - pooled))
            + z_power * math.sqrt(baseline * (1 - baseline) + p1 * (1 - p1))
        ) ** 2
        return math.ceil(numerator / (p1 - baseline) ** 2)

    @staticmethod
    def continuous_sample_size(
        *, variance_estimate: float, delta: float, alpha: float, power: float
    ) -> int:
        if variance_estimate <= 0 or delta <= 0:
            raise ValueError("variance and delta must be positive")
        normal = NormalDist()
        return math.ceil(
            2
            * variance_estimate
            * (normal.inv_cdf(1 - alpha / 2) + normal.inv_cdf(power)) ** 2
            / delta**2
        )

    def create_experiment(self, merchant_id: UUID, opportunity_id: UUID) -> ExperimentSpec:
        self._assert_tenant(merchant_id)
        opportunity = self.opportunities[opportunity_id]
        customer_ids = tuple(
            UUID(value) for value in opportunity.affected_population["customer_ids"]
        )
        experiment_id = uuid5(DEMO_NAMESPACE, f"{merchant_id}:experiment:v1")
        arms = (
            ExperimentArm(
                id=uuid5(experiment_id, "control"),
                name="Control",
                action_type="no_action",
                parameters={},
                allocation_probability=1 / 3,
                is_control=True,
            ),
            ExperimentArm(
                id=uuid5(experiment_id, "shipping"),
                name="Free shipping",
                action_type="free_shipping",
                parameters={},
                allocation_probability=1 / 3,
            ),
            ExperimentArm(
                id=uuid5(experiment_id, "discount"),
                name="10% offer",
                action_type="discount",
                parameters={"depth": 0.10},
                allocation_probability=1 / 3,
            ),
        )
        spec = ExperimentSpec(
            id=experiment_id,
            merchant_id=merchant_id,
            opportunity_id=opportunity_id,
            name="High-intent repeat recovery test",
            eligibility_customer_ids=customer_ids,
            primary_outcome="contribution_profit_per_eligible_customer",
            outcome_window_days=30,
            randomization_seed="demo-seed-v1",
            arms=arms,
            alpha=0.05,
            power=0.80,
        )
        self.experiments[spec.id] = spec
        return spec

    def freeze_experiment(
        self, merchant_id: UUID, experiment_id: UUID, *, at: datetime
    ) -> ExperimentSpec:
        self._assert_tenant(merchant_id)
        spec = self.experiments[experiment_id]
        if spec.frozen_at is not None:
            return spec
        payload = spec.model_dump(mode="json", exclude={"frozen_at", "spec_hash"})
        frozen = spec.model_copy(update={"frozen_at": at, "spec_hash": _hash(payload)})
        self.experiments[experiment_id] = frozen
        self.ledger.append(
            {
                "type": "PRE_OUTCOME_EXPERIMENT",
                "merchant_id": str(merchant_id),
                "experiment_id": str(experiment_id),
                "recorded_at": at.isoformat(),
                "spec_hash": frozen.spec_hash,
                "recommendation": "TEST_THIS",
                "causal_estimate": None,
                "label": "SYNTHETIC DEMO — NOT COMMERCIAL EVIDENCE"
                if self.synthetic_demo
                else None,
            }
        )
        return frozen

    def assign(
        self, merchant_id: UUID, experiment_id: UUID, *, at: datetime
    ) -> tuple[Assignment, ...]:
        self._assert_tenant(merchant_id)
        if experiment_id in self.assignments:
            return self.assignments[experiment_id]
        spec = self.experiments[experiment_id]
        if spec.frozen_at is None:
            raise RuntimeError("experiment must be frozen before assignment")
        cumulative = np.cumsum([arm.allocation_probability for arm in spec.arms])
        rows: list[Assignment] = []
        for customer_id in spec.eligibility_customer_ids:
            digest = hmac.new(
                spec.randomization_seed.encode(),
                f"{merchant_id}|{experiment_id}|{customer_id}".encode(),
                hashlib.sha256,
            ).digest()
            uniform = int.from_bytes(digest[:8], "big") / 2**64
            index = min(int(np.searchsorted(cumulative, uniform, side="right")), len(spec.arms) - 1)
            arm = spec.arms[index]
            rows.append(
                Assignment(
                    experiment_id=experiment_id,
                    merchant_id=merchant_id,
                    customer_id=customer_id,
                    arm_id=arm.id,
                    assigned_at=at,
                    assignment_probability=arm.allocation_probability,
                    assignment_hash=hashlib.sha256(digest).hexdigest(),
                )
            )
        self.assignments[experiment_id] = tuple(rows)
        return tuple(rows)

    def reveal_demo_outcomes(
        self, merchant_id: UUID, experiment_id: UUID
    ) -> tuple[ExperimentOutcome, ...]:
        self._assert_tenant(merchant_id)
        if not self.synthetic_demo:
            raise RuntimeError("real outcomes must be ingested, never simulated")
        assignments = self.assignments[experiment_id]
        spec = self.experiments[experiment_id]
        arm_by_id = {arm.id: arm for arm in spec.arms}
        rows: list[ExperimentOutcome] = []
        for assignment in assignments:
            arm = arm_by_id[assignment.arm_id]
            rng = np.random.default_rng(int(assignment.assignment_hash[:16], 16))
            effect = {"no_action": 0.0, "free_shipping": 0.95, "discount": 0.20}[arm.action_type]
            gross = max(0.0, float(rng.normal(7.0 + effect * 2.0, 5.0)))
            discount = gross * 0.10 if arm.action_type == "discount" else 0.0
            shipping_cost = 0.65 if arm.action_type == "free_shipping" else 0.25
            profit = contribution_profit(
                gross_item_sales=gross,
                line_discounts=discount,
                refunds=0.0,
                shipping_revenue=0.0,
                cogs=gross * 0.42,
                merchant_shipping_cost=shipping_cost,
                campaign_variable_cost=0.05,
                payment_processing_cost=gross * 0.025,
            )
            rows.append(
                ExperimentOutcome(
                    experiment_id=experiment_id,
                    merchant_id=merchant_id,
                    customer_id=assignment.customer_id,
                    purchase=int(gross > 2),
                    order_count=int(gross > 2),
                    gross_item_sales=gross,
                    line_discounts=discount,
                    refunds=0.0,
                    shipping_revenue=0.0,
                    cogs=gross * 0.42,
                    merchant_shipping_cost=shipping_cost,
                    campaign_variable_cost=0.05,
                    payment_processing_cost=gross * 0.025,
                    contribution_profit=profit,
                )
            )
        self.outcomes[experiment_id] = tuple(rows)
        return tuple(rows)

    def analyze(self, merchant_id: UUID, experiment_id: UUID) -> tuple[ExperimentResult, ...]:
        self._assert_tenant(merchant_id)
        spec = self.experiments[experiment_id]
        assignments = self.assignments[experiment_id]
        outcomes = {row.customer_id: row for row in self.outcomes[experiment_id]}
        arm_by_customer = {row.customer_id: row.arm_id for row in assignments}
        control = next(arm for arm in spec.arms if arm.is_control)
        control_values = [
            float(outcomes[c].contribution_profit or 0.0)
            for c, arm in arm_by_customer.items()
            if arm == control.id and outcomes[c].contribution_profit is not None
        ]
        results: list[ExperimentResult] = []
        for treatment in (arm for arm in spec.arms if not arm.is_control):
            treatment_values = [
                float(outcomes[c].contribution_profit or 0.0)
                for c, arm in arm_by_customer.items()
                if arm == treatment.id and outcomes[c].contribution_profit is not None
            ]
            effect = mean(treatment_values) - mean(control_values)
            se = math.sqrt(
                variance(treatment_values) / len(treatment_values)
                + variance(control_values) / len(control_values)
            )
            result = ExperimentResult(
                experiment_id=experiment_id,
                estimator="RANDOMIZED_DIFFERENCE_IN_MEANS_ITT",
                control_arm_id=control.id,
                treatment_arm_id=treatment.id,
                sample_control=len(control_values),
                sample_treatment=len(treatment_values),
                effect_per_customer=effect,
                standard_error=se,
                confidence_interval=(effect - 1.96 * se, effect + 1.96 * se),
                total_incremental_effect=effect * len(spec.eligibility_customer_ids),
                evidence=EvidenceLabel.SIMULATED_ONLY
                if self.synthetic_demo
                else EvidenceLabel.RANDOMIZED_CAUSAL,
                economics_status="IDENTIFIED",
            )
            results.append(result)
        self.results[experiment_id] = tuple(results)
        self.ledger.append(
            {
                "type": "EXPERIMENT_RESULT",
                "merchant_id": str(merchant_id),
                "experiment_id": str(experiment_id),
                "recorded_at": datetime.now(UTC).isoformat(),
                "results": [r.model_dump(mode="json") for r in results],
                "append_only": True,
            }
        )
        best = max(results, key=lambda result: result.effect_per_customer)
        treatment_arm = next(arm for arm in spec.arms if arm.id == best.treatment_arm_id)
        learning = MerchantLearningRecord(
            merchant_id=merchant_id,
            experiment_id=experiment_id,
            pre_action_state={
                "opportunity_id": str(spec.opportunity_id),
                "lifecycle": "established",
                "value_band": "medium",
                "intent_band": "high",
            },
            action_definition={
                "treatment_arm_id": str(best.treatment_arm_id),
                "action_type": treatment_arm.action_type,
            },
            outcome_definition={
                "primary": spec.primary_outcome,
                "window_days": spec.outcome_window_days,
            },
            estimated_effect={
                "per_customer": best.effect_per_customer,
                "total": best.total_incremental_effect,
                "sample_size": best.sample_control + best.sample_treatment,
            },
            uncertainty={"ci": best.confidence_interval, "se": best.standard_error},
            economics={"status": best.economics_status},
            evidence=EvidenceLabel.SIMULATED_ONLY
            if self.synthetic_demo
            else EvidenceLabel.RANDOMIZED_CAUSAL,
            recorded_at=datetime.now(UTC),
        )
        self.learning_records.append(learning)
        return tuple(results)


def build_demo_service(
    *, as_of: datetime | None = None, customer_count: int = 180
) -> MerchantValidationService:
    now = as_of or datetime(2026, 8, 1, tzinfo=UTC)
    organization_id = uuid5(DEMO_NAMESPACE, "demo-organization")
    merchant_id = uuid5(DEMO_NAMESPACE, "demo-merchant")
    service = MerchantValidationService(organization_id, merchant_id, synthetic_demo=True)
    for index in range(customer_count):
        customer_id = uuid5(DEMO_NAMESPACE, f"customer-{index}")
        service.customers[customer_id] = {"first_seen_at": now - timedelta(days=400 + index % 100)}
        for order_index in range(2 + index % 3):
            ordered_at = now - timedelta(days=150 + order_index * 55 + index % 20)
            net_sales = 55.0 + index % 30
            service.orders.append(
                {
                    "external_order_id": f"order-{index}-{order_index}",
                    "customer_id": customer_id,
                    "ordered_at": ordered_at,
                    "observed_at": ordered_at,
                    "net_sales": net_sales,
                    "category": "core",
                    "cogs": net_sales * 0.42,
                    "profit": net_sales * 0.45,
                }
            )
        for event_index in range(3):
            occurred_at = now - timedelta(days=3 + event_index + index % 5)
            service.ingest_event(
                merchant_id,
                {
                    "external_event_id": f"event-{index}-{event_index}",
                    "customer_id": customer_id,
                    "event_type": "add_to_cart" if event_index == 0 else "product_view",
                    "occurred_at": occurred_at,
                    "observed_at": occurred_at,
                },
            )
    # One documented historical randomized record enables causal-history readiness without
    # being used to fabricate a causal winner for the new action types.
    service.historical_assignments.append({"experiment_id": "historical-demo", "probability": 0.5})
    return service
