from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from decision_engine.benchmark.time_machine import TimeMachineBenchmark
from decision_engine.forecasting.baseline import BaselineKind, SeasonalBaseline
from decision_engine.metrics.forecasting import forecast_metrics


@dataclass(frozen=True)
class ForecastBenchmarkResult:
    cutoff: str
    horizon_days: int
    observations: int
    models: dict[str, dict[str, float]]


def run_baseline_benchmark(
    data: pl.DataFrame, cutoff: datetime, *, horizon_days: int = 7
) -> ForecastBenchmarkResult:
    machine = TimeMachineBenchmark(data).freeze_at(cutoff)
    history = machine.history()
    predictions = {
        kind.value: SeasonalBaseline(kind).predict(history, horizon_days) for kind in BaselineKind
    }
    machine.lock_prediction(predictions)
    future = machine.reveal_outcome(start=cutoff, end=cutoff + timedelta(days=horizon_days - 1))
    actual = future.sort("timestamp")["outcome"].to_numpy().astype(float)
    if actual.size != horizon_days:
        raise ValueError(f"expected {horizon_days} outcome rows, got {actual.size}")
    train = history["outcome"].to_numpy().astype(float)
    metrics = {name: forecast_metrics(actual, pred, train) for name, pred in predictions.items()}
    return ForecastBenchmarkResult(cutoff.isoformat(), horizon_days, int(actual.size), metrics)


def write_report(result: ForecastBenchmarkResult, output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = directory / "benchmark.json", directory / "benchmark.md"
    json_path.write_text(json.dumps(asdict(result), indent=2, sort_keys=True))
    rows = [
        "# Decision Engine Forecast Benchmark",
        "",
        f"Cutoff: {result.cutoff}",
        f"Horizon: {result.horizon_days} days",
        "",
        "| Model | MAE | RMSE | WAPE | MASE |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, metrics in result.models.items():
        metric_cells = " | ".join(f"{metrics[key]:.4f}" for key in ("mae", "rmse", "wape", "mase"))
        rows.append(f"| {name} | {metric_cells} |")
    markdown_path.write_text("\n".join(rows) + "\n")
    return json_path, markdown_path
