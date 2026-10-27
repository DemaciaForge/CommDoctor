import math

import pytest

import stage13_lms
from tests.oracles.stage13_lms_oracle import run as oracle_run


def test_production_update_matches_independent_reference():
    samples = tuple(float(value) for value in (1, 0, 0, 0, 0, 0, 1, 0, 0, 0))
    targets = (1.0, -1.0)
    expected_weights, expected_errors = oracle_run(samples, targets, 0.2, taps=5)
    import numpy as np
    weights = np.zeros(5, dtype=np.float64)
    errors = []
    for row, desired in enumerate(targets):
        window = np.asarray(samples[row * 5:(row + 1) * 5])
        error, weights = stage13_lms.lms_step(weights, window, desired, 0.2)
        errors.append(error * error)
    assert tuple(weights) == pytest.approx(expected_weights)
    assert tuple(errors) == pytest.approx(expected_errors)


def test_experiment_is_reproducible_and_keeps_training_separate_from_payload():
    first = stage13_lms.run_experiment(seed=7, eb_n0_db=8, n_training_symbols=32, n_payload_symbols=128, mu=0.01)
    second = stage13_lms.run_experiment(seed=7, eb_n0_db=8, n_training_symbols=32, n_payload_symbols=128, mu=0.01)
    assert first == second
    assert first["contract"]["decision_delay_symbols"] == 2
    assert first["contract"]["training_samples"] == 32
    assert first["contract"]["evaluation_indices"] == list(range(32, 160))
    assert first["results"]["raw"]["compared"] == first["results"]["lms"]["compared"] == 128
    assert first["contract"]["same_channel_and_noise"] is True


@pytest.mark.parametrize("kwargs", [
    {"mu": 0}, {"mu": -0.1}, {"mu": math.inf}, {"mu": math.nan},
    {"n_training_symbols": 15}, {"n_training_symbols": 61},
    {"n_payload_symbols": 127}, {"n_payload_symbols": 4097}, {"seed": -1},
])
def test_invalid_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        stage13_lms.run_experiment(**kwargs)
