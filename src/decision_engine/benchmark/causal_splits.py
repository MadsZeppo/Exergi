from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChronologicalFold:
    train_indices: np.ndarray
    evaluation_indices: np.ndarray


def chronological_cross_fitting_folds(
    timestamps: np.ndarray, *, n_folds: int = 3, minimum_train_fraction: float = 0.4
) -> list[ChronologicalFold]:
    """Expanding nuisance-training blocks followed by strictly future evaluation blocks."""
    values = np.asarray(timestamps)
    if values.ndim != 1 or values.size < n_folds + 2:
        raise ValueError("insufficient one-dimensional timestamps")
    order = np.argsort(values, kind="stable")
    first_eval = max(1, int(values.size * minimum_train_fraction))
    blocks = np.array_split(order[first_eval:], n_folds)
    result: list[ChronologicalFold] = []
    for block in blocks:
        if not block.size:
            continue
        train = order[values[order] < values[block].min()]
        if train.size:
            result.append(ChronologicalFold(train, block))
    return result
