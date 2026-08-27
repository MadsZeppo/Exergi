#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime

import polars as pl

from decision_engine.benchmark.runner import run_baseline_benchmark, write_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a leak-safe baseline benchmark on canonical parquet"
    )
    parser.add_argument("dataset", help="Canonical parquet with timestamp, observed_at, outcome")
    parser.add_argument("--cutoff", required=True, type=datetime.fromisoformat)
    parser.add_argument("--horizon", type=int, default=7)
    parser.add_argument("--output", default="artifacts/benchmarks/latest")
    args = parser.parse_args()
    result = run_baseline_benchmark(
        pl.read_parquet(args.dataset), args.cutoff, horizon_days=args.horizon
    )
    paths = write_report(result, args.output)
    print(f"Wrote {paths[0]} and {paths[1]}")


if __name__ == "__main__":
    main()
