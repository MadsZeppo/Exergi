from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from commercial_twin.presentation import DecisionOpportunity, build_commercial_twin_view
from commercial_twin.schemas import GeographicExposure
from commercial_twin.world_state import get_current_world_state
from decision_engine.causal.challengers import DoWhyValidator, EconMLContinuousDMLChallenger
from domains.commerce.actions import DiscountAction
from domains.commerce.fixtures import build_synthetic_commercial_twin

EXPOSURE = (
    GeographicExposure(geography="CA", weight=0.31),
    GeographicExposure(geography="TX", weight=0.18),
    GeographicExposure(geography="NY", weight=0.11),
    GeographicExposure(geography="FL", weight=0.08),
    GeographicExposure(geography="IL", weight=0.07),
    GeographicExposure(geography="US", weight=0.25),
)


def main() -> None:
    now = datetime.now(UTC)
    current_dir = Path("artifacts/world_state/current")
    demo_dir = Path("artifacts/commercial_twin/product_demo")
    benchmark_dir = Path("artifacts/benchmarks/mt_lift")
    for path in (current_dir, demo_dir, benchmark_dir):
        path.mkdir(parents=True, exist_ok=True)
    world = get_current_world_state(EXPOSURE, "food_at_home")
    (current_dir / "current_us_exposure_snapshot.json").write_text(
        world.model_dump_json(indent=2), encoding="utf-8"
    )
    provenance = {
        "generated_at": now.isoformat(),
        "label": "REAL WORLD SIGNALS",
        "sources": sorted({signal.source for signal in world.signals}),
        "series": sorted({signal.series_id for signal in world.signals if signal.series_id}),
        "rule": "available_at <= snapshot as_of",
        "warning": "latest-revised series are current context, not strict historical vintages",
    }
    (current_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    fixture = build_synthetic_commercial_twin(seed=42)
    twin = fixture.twin
    twin.state = twin.state.model_copy(update={"world_state": world, "as_of": now})
    actions = tuple(
        DiscountAction(
            action_id=f"discount-{int(depth * 100)}",
            scope="all_products",
            start=now,
            end=now + timedelta(days=7),
            discount_depth=depth,
        )
        for depth in (0.05, 0.10, 0.20)
    )
    results = twin.compare(actions)
    profit = {
        result.candidate_action.action_id: next(
            item.mean
            for item in result.outcome_distributions
            if item.outcome_name == "contribution_profit"
        )
        for result in results
    }
    candidate = max(results, key=lambda item: profit[item.candidate_action.action_id])
    baseline = results[1]
    opportunity = DecisionOpportunity(
        decision_type="discount_review",
        scope="synthetic modern US consumer brand",
        candidate_action=candidate.candidate_action,
        baseline_action=baseline.candidate_action,
        expected_value_delta=(
            profit[candidate.candidate_action.action_id]
            - profit[baseline.candidate_action.action_id]
        ),
        evidence={
            "behavior": "SYNTHETIC",
            "world_state": "REAL CURRENT SIGNALS",
            "disposition": candidate.disposition.value,
        },
        reason="highest modeled contribution profit among reviewed supported candidates",
        priority="REVIEW_ONLY",
    )
    view = build_commercial_twin_view(
        twin.snapshot(),
        "What happens if this brand runs a 5%, 10%, or 20% discount now?",
        results,
        opportunity,
    )
    payload = view.model_dump(mode="json")
    payload["evidence_label"] = "SYNTHETIC BEHAVIOR — REAL WORLD SIGNALS"
    payload["commercial_validity"] = "NOT_ESTABLISHED"
    (demo_dir / "commercial_twin_view.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (demo_dir / "frozen_simulations.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in results], indent=2),
        encoding="utf-8",
    )
    integration = {
        "dowhy": "AVAILABLE" if DoWhyValidator.available() else "NOT_INSTALLED",
        "econml": ("AVAILABLE" if EconMLContinuousDMLChallenger.available() else "NOT_INSTALLED"),
    }
    (benchmark_dir / "integration_status.json").write_text(
        json.dumps(
            {
                "status": "READY_FOR_DATA",
                "dataset_present": False,
                "published_rows": 5_541_842,
                "published_features": 99,
                "treatment_arms": 5,
                "access": "publisher Google Drive link requires external retrieval",
                "license": "NO EXPLICIT LICENSE FOUND IN PUBLISHER REPOSITORY",
                "benchmark_run": False,
                "optional_challengers": integration,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
