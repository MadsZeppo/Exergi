"""Compact probabilistic models for JDsearch event-time customer dynamics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import log_loss
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from commercial_twin.jdsearch_behavioral import EVENT_TYPES
from commercial_twin.jdsearch_dynamics import HORIZONS, SEQUENCE_LENGTH


def sequence_arrays(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    types = frame[[f"sequence_type_{index}" for index in range(SEQUENCE_LENGTH)]].to_numpy(int)
    intervals = frame[[f"sequence_interval_{index}" for index in range(SEQUENCE_LENGTH)]].to_numpy(
        np.float32
    )
    return types, intervals


class PredictiveGRU(nn.Module):  # type: ignore[misc]  # optional torch types may be unavailable
    def __init__(self, dimension: int, *, use_intervals: bool = True) -> None:
        super().__init__()
        self.dimension = dimension
        self.use_intervals = use_intervals
        self.embedding = nn.Embedding(5, 4, padding_idx=0)
        self.gru = nn.GRU(5 if use_intervals else 4, dimension, batch_first=True)
        self.next_event = nn.Linear(dimension, 4)
        self.binary = nn.ModuleDict(
            {
                f"{kind}_{horizon}": nn.Linear(dimension, 1)
                for kind in ("ord", "cart", "click")
                for horizon in HORIZONS
            }
        )
        self.mix = nn.ModuleDict({str(horizon): nn.Linear(dimension, 4) for horizon in HORIZONS})

    def encode(self, types: torch.Tensor, intervals: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(torch.clamp(types + 1, 0, 4))
        inputs = (
            torch.cat([embedded, intervals.unsqueeze(-1)], dim=-1)
            if self.use_intervals
            else embedded
        )
        _, hidden = self.gru(inputs)
        return hidden[-1]

    def forward(self, types: torch.Tensor, intervals: torch.Tensor) -> dict[str, torch.Tensor]:
        state = self.encode(types, intervals)
        result = {"state": state, "next_event": self.next_event(state)}
        result.update({key: head(state).squeeze(-1) for key, head in self.binary.items()})
        result.update({f"mix_{key}": head(state) for key, head in self.mix.items()})
        return result


def target_arrays(targets: pd.DataFrame) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {"next_event": targets["next_event"].to_numpy(np.int64)}
    for kind in ("ord", "cart", "click"):
        for horizon in HORIZONS:
            result[f"{kind}_{horizon}"] = targets[f"{kind}_any_{horizon}"].to_numpy(np.float32)
    for horizon in HORIZONS:
        result[f"mix_{horizon}"] = targets[
            [f"{kind.lower()}_share_{horizon}" for kind in EVENT_TYPES]
        ].to_numpy(np.float32)
    return result


def fit_gru(
    features: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    dimension: int,
    use_intervals: bool,
    seed: int = 42,
    epochs: int = 4,
    maximum_rows: int = 200_000,
) -> PredictiveGRU:
    # Small recurrent batches are dramatically slower with excessive CPU thread fan-out.
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    np.random.seed(seed)
    if len(features) > maximum_rows:
        selected = np.random.default_rng(seed).choice(len(features), maximum_rows, replace=False)
        features, targets = features.iloc[selected], targets.iloc[selected]
    types, intervals = sequence_arrays(features)
    target = target_arrays(targets)
    tensors = [
        torch.from_numpy(types),
        torch.from_numpy(intervals),
        torch.from_numpy(target["next_event"]),
    ]
    tensors.extend(
        torch.from_numpy(target[f"{kind}_{horizon}"])
        for kind in ("ord", "cart", "click")
        for horizon in HORIZONS
    )
    tensors.extend(torch.from_numpy(target[f"mix_{horizon}"]) for horizon in HORIZONS)
    loader = DataLoader(TensorDataset(*tensors), batch_size=1024, shuffle=True)
    model = PredictiveGRU(dimension, use_intervals=use_intervals)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.003, weight_decay=1e-4)
    bce, ce = nn.BCEWithLogitsLoss(), nn.CrossEntropyLoss()
    for _ in range(epochs):
        model.train()
        for batch in loader:
            output = model(batch[0], batch[1])
            loss = ce(output["next_event"], batch[2])
            offset = 3
            for kind in ("ord", "cart", "click"):
                for horizon in HORIZONS:
                    loss = loss + 0.35 * bce(output[f"{kind}_{horizon}"], batch[offset])
                    offset += 1
            for horizon in HORIZONS:
                loss = loss + 0.25 * torch.mean(
                    torch.sum(-batch[offset] * torch.log_softmax(output[f"mix_{horizon}"], -1), -1)
                )
                offset += 1
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
    return model.eval()


@dataclass(frozen=True)
class GRUPredictions:
    state: np.ndarray
    next_event: np.ndarray
    binary: dict[str, np.ndarray]
    mix: dict[int, np.ndarray]


def predict_gru(
    model: PredictiveGRU, features: pd.DataFrame, batch_size: int = 4096
) -> GRUPredictions:
    types, intervals = sequence_arrays(features)
    states, events = [], []
    binary: dict[str, list[np.ndarray]] = {
        f"{kind}_{horizon}": [] for kind in ("ord", "cart", "click") for horizon in HORIZONS
    }
    mixes: dict[int, list[np.ndarray]] = {horizon: [] for horizon in HORIZONS}
    with torch.no_grad():
        for start in range(0, len(features), batch_size):
            output = model(
                torch.from_numpy(types[start : start + batch_size]),
                torch.from_numpy(intervals[start : start + batch_size]),
            )
            states.append(output["state"].numpy())
            events.append(torch.softmax(output["next_event"], -1).numpy())
            for key in binary:
                binary[key].append(torch.sigmoid(output[key]).numpy())
            for horizon in HORIZONS:
                mixes[horizon].append(torch.softmax(output[f"mix_{horizon}"], -1).numpy())
    return GRUPredictions(
        np.concatenate(states),
        np.concatenate(events),
        {key: np.concatenate(value) for key, value in binary.items()},
        {key: np.concatenate(value) for key, value in mixes.items()},
    )


def select_dimension(results: pd.DataFrame) -> int:
    best = float(results["composite_score"].max())
    eligible = results[results.composite_score >= 0.99 * best]
    return int(eligible.sort_values("dimension").iloc[0].dimension)


def relative_log_loss_gain(y: np.ndarray, base: np.ndarray, challenger: np.ndarray) -> float:
    base_loss = log_loss(y, base)
    return float((base_loss - log_loss(y, challenger)) / base_loss)
