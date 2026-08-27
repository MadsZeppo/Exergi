import numpy as np

from decision_engine.benchmark.causal_splits import chronological_cross_fitting_folds


def test_time_aware_folds_are_strictly_ordered() -> None:
    timestamps = np.arange(100)
    folds = chronological_cross_fitting_folds(timestamps, n_folds=3)
    assert len(folds) == 3
    for fold in folds:
        assert timestamps[fold.train_indices].max() < timestamps[fold.evaluation_indices].min()
