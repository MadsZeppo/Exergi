#!/usr/bin/env python3
import argparse
from pathlib import Path

from decision_engine.benchmark.hillstrom import run_hillstrom_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Hillstrom randomized benchmark")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    run_id = f"seed-{args.seed}-bootstrap-{args.bootstrap_samples}"
    output = Path(args.output_dir or f"artifacts/benchmarks/hillstrom/{run_id}")
    summary = run_hillstrom_benchmark(
        path="data/raw/hillstrom/hillstrom.csv",
        output_dir=output,
        seed=args.seed,
        bootstrap_samples=args.bootstrap_samples,
    )
    print(f"Wrote {output / 'summary.json'}")
    print(summary["act_experiment_abstain"], summary["recommended_action_pre_reveal"])


if __name__ == "__main__":
    main()
