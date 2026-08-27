#!/usr/bin/env python3
from decision_engine.causal.dr_learner import CrossFittedDRLearner
from decision_engine.causal.synthetic import generate_confounded_treatment_data
from decision_engine.metrics.causal import ate_error, pehe


def main() -> None:
    data = generate_confounded_treatment_data()
    estimate = CrossFittedDRLearner().fit(data.x, data.treatment, data.outcome).effect(data.x)
    print(
        {
            "ate_error": ate_error(estimate, data.true_effect),
            "pehe": pehe(estimate, data.true_effect),
        }
    )


if __name__ == "__main__":
    main()
