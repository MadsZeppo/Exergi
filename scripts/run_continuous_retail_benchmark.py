#!/usr/bin/env python3
import argparse

from decision_engine.benchmark.continuous_retail import run_continuous_retail_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Run truth-known continuous retail worlds")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="6 worlds and 8 bootstraps")
    mode.add_argument("--definitive", action="store_true", help="24 worlds and 100 bootstraps")
    parser.add_argument("--seeds", type=int)
    parser.add_argument("--bootstrap-replicates", type=int)
    parser.add_argument(
        "--output-dir", default="artifacts/benchmarks/continuous-retail/seed-suite-20"
    )
    args = parser.parse_args()
    selected_mode = "definitive" if args.definitive else "quick"
    seeds = args.seeds if args.seeds is not None else (24 if args.definitive else 6)
    bootstraps = (
        args.bootstrap_replicates
        if args.bootstrap_replicates is not None
        else (100 if args.definitive else 8)
    )
    summary = run_continuous_retail_benchmark(
        args.output_dir,
        seeds=seeds,
        bootstrap_replicates=bootstraps,
        mode=selected_mode,
    )
    print(summary)


if __name__ == "__main__":
    main()
