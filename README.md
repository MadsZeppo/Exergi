# Commercial Twin

Commercial Twin is a scientific decision system for simulating commercial actions before they
are taken. It places a typed product layer over the repository's leak-safe forecasting, causal
estimation, uncertainty, support gating, economics, benchmarks, Prediction Ledger, and model
registry.

The first implemented action is continuous discount depth. The system estimates a causal response
distribution under explicit assumptions, transforms demand into contribution profit, evaluates
conditional treatment support, and returns `ACT`, `EXPERIMENT`, or `ABSTAIN`. It never treats a
predictive optimum as causal proof.

## Architecture

The repository keeps three boundaries:

- `decision_engine`: generic scientific primitives and the established mathematical core.
- `commercial_twin`: immutable commercial state, behavior-model protocol, twin orchestration,
  readiness, calibration, cohorts, and factory.
- `domains.commerce`: typed commercial actions and the continuous-discount behavior adapter.

The generic `DecisionProblem` describes state, candidate actions, outcomes, utility, constraints,
horizon, and decision context. A `CommercialTwin` snapshots customer, company, and world state,
then produces a `SimulationResult` with outcome distributions, assumptions, support, uncertainty,
model versions, and a decision disposition.

## Scientific invariants

- Event time, observation time, decision time, and action time are explicit and timezone-aware.
- Controls are declared pre-treatment; post-treatment columns are rejected by the causal core.
- Chronological cross-fitting prevents nuisance predictions on their own training rows.
- Conditional treatment density participates in the continuous doubly robust correction.
- An unsupported candidate can never return `ACT`.
- Oracle arrays from synthetic worlds remain evaluation-only and are rejected from twin input.
- Hidden confounding is not claimed to be solved.
- Estimation and contribution-profit transformation remain separate concepts.
- Readiness is decomposed by capability and evidence component, never presented as a fake scalar.

## Commercial state

- `CustomerState`: deterministic cohort-level recency, frequency, monetary value, affinities,
  promotion response, and retention fields; no raw PII.
- `CompanyState`: products, prices, costs, inventory, campaigns, offers, channels, and fulfillment.
- `WorldState`: time-stamped market signals with source, geography, confidence, and provenance.
- `CommercialState`: the immutable combination used for one simulation snapshot.

The synthetic fixture demonstrates that identical customer and company state can produce different
outcomes when observed world state changes. This is a transparent deterministic interaction, not an
LLM agent or a synthetic customer society.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check .
mypy
```

Run the research cockpit:

```bash
uv run streamlit run apps/research_dashboard.py
```

All demo views are labelled **SYNTHETIC — NOT COMMERCIAL EVIDENCE**.

## Example

```python
from datetime import UTC, datetime, timedelta

from domains.commerce.actions import DiscountAction
from domains.commerce.fixtures import build_synthetic_commercial_twin

fixture = build_synthetic_commercial_twin(seed=42)
now = datetime.now(UTC)
action = DiscountAction(
    action_id="discount-10",
    scope="all_products",
    start=now,
    end=now + timedelta(days=7),
    discount_depth=0.10,
)
result = fixture.twin.simulate(action)
print(result.disposition, result.outcome_distributions)
```

The fixture retains oracle truth separately for evaluation. `canonical_history` and twin state do
not contain it.

## Persistence and learning loop

The append-only Prediction Ledger now supports both legacy predictions and generic twin simulation
snapshots. After outcomes arrive, `CommercialTwin.update(...)` records prediction errors and adds a
decision-performance record to the registry. This creates the loop:

`snapshot → simulate → decide → observe → calibrate → evaluate`

The current interval layer in the commercial adapter uses cross-fitted residual uncertainty and is
explicitly marked as requiring prospective calibration. Existing bootstrap counterfactual
calibration remains in the scientific benchmark layer.

## Current scope and limitations

Implemented now: continuous discount simulation, conditional support, contribution-profit outcomes,
cohort state, world-state interaction, readiness, calibration records, and compatible persistence.

Typed but not behaviorally implemented: price change, free shipping, and general promotion actions.
Product launch is not ready. No Shopify/Meta/Klaviyo integration, UI product, LLM agents, world
model, reinforcement learning, supply-chain optimization, individualized pricing, or autonomous
execution is included.

The system is not “production ready.” Observational causal validity still depends on measured
confounding assumptions, positivity, data quality, stable measurement, correct economic inputs, and
prospective calibration. The dashboard and synthetic benchmarks are research evidence only.

See [`docs/commercial_twin_refactor_audit.md`](docs/commercial_twin_refactor_audit.md) for the
pre-refactor inventory and migration decisions.
# Exergi
