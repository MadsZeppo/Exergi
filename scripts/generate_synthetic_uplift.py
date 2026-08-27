from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from decision_engine.causal.layer3_validation import generate_synthetic_uplift


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic Layer 3 oracle data")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--customers", type=int, default=20_000)
    parser.add_argument("--output", type=Path, default=Path("data/synthetic/layer3"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for scenario in ("randomized", "confounded", "placebo"):
        generated = generate_synthetic_uplift(
            seed=args.seed, n_customers=args.customers, scenario=scenario
        )
        columns = {f"x{index}": generated.features[:, index] for index in range(7)}
        pl.DataFrame(
            {
                "customer_id": generated.customer_id,
                **columns,
                "segment": generated.segment,
                "treatment": generated.treatment,
                "outcome": generated.outcome,
                "oracle_true_effect_evaluation_only": generated.true_effect,
                "oracle_true_propensity_evaluation_only": generated.true_propensity,
            }
        ).write_parquet(args.output / f"{scenario}-seed-{args.seed}.parquet")
    print(args.output)


if __name__ == "__main__":
    main()
