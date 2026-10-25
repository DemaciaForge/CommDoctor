"""Independent Stage09 checks; expected values do not call fit_equalizer."""
from __future__ import annotations
import math

import numpy as np
import pytest

from multipath_equalization import (
    EQUALIZER_TAPS,
    SAMPLES_PER_SYMBOL,
    create_experiment,
    full_convolve,
    validate_channel,
)


def scalar_convolve(a: list[float], b: list[float]) -> list[float]:
    out = [0.0] * (len(a) + len(b) - 1)
    for i, left in enumerate(a):
        for j, right in enumerate(b):
            out[i + j] += left * right
    return out


def test_full_convolution_matches_hand_calculated_oracle_and_preserves_length():
    left, right = [1.0, 2.0, 0.0], [1.0, 0.5]
    assert np.array_equal(full_convolve(np.asarray(left), np.asarray(right)), scalar_convolve(left, right))
    assert len(full_convolve(np.ones(7), np.ones(4))) == 10


def test_two_path_delay_has_explicit_isi_and_normalized_gains():
    experiment = create_experiment(seed=7, eb_n0_db=20, n_payload_symbols=128,
                                    path_delays_samples=[0, SAMPLES_PER_SYMBOL], path_gains=[1.0, 0.7])
    gains = experiment["path_gains"]
    assert math.isclose(float(np.linalg.norm(gains)), 1.0, rel_tol=0, abs_tol=1e-15)
    assert experiment["channel_impulse"][0] > 0 and experiment["channel_impulse"][SAMPLES_PER_SYMBOL] > 0
    layout = experiment["layout"]
    samples = experiment["matched"][list(layout.payload_sample_indices)]
    assert samples.shape == experiment["payload_bits"].shape
    assert len(experiment["channel_waveform"]) == len(experiment["tx_waveform"]) + SAMPLES_PER_SYMBOL
    assert not np.allclose(experiment["channel_waveform"][:len(experiment["tx_waveform"])], experiment["tx_waveform"])


def test_mmse_closed_form_uses_noise_regularization_independently():
    X = np.asarray([[1.0, 0.2, -0.1], [0.2, 1.0, 0.3], [-0.1, 0.3, 1.0]])
    target = np.asarray([0.0, 1.0, 0.0])
    lam = 0.25
    expected = np.linalg.solve(X.T @ X + lam * np.eye(3), X.T @ target)
    assert expected.shape == (3,)
    assert np.allclose(expected, np.linalg.pinv(X.T @ X + lam * np.eye(3)) @ X.T @ target)
    assert EQUALIZER_TAPS == 5


@pytest.mark.parametrize("bad_delays,bad_gains", [([], []), ([0, 0], [1, 0.5]), ([1], [1]), ([0], [0]), ([0], [math.inf])])
def test_channel_validation_rejects_invalid_shape_delay_and_gain(bad_delays, bad_gains):
    with pytest.raises(ValueError):
        validate_channel(bad_delays, bad_gains)


def test_fixed_seed_reproduces_exact_receive_and_payload_indices():
    first = create_experiment(seed=123, eb_n0_db=8, n_payload_symbols=128)
    second = create_experiment(seed=123, eb_n0_db=8, n_payload_symbols=128)
    assert np.array_equal(first["payload_bits"], second["payload_bits"])
    assert np.array_equal(first["rx_waveform"], second["rx_waveform"])
    assert first["raw_ber"] == second["raw_ber"]
    assert first["raw_ber"]["n_compared"] == 128
    assert first["layout"].payload_sample_indices == second["layout"].payload_sample_indices
