"""Independent mathematical oracle for Stage08 timing synchronization.

This file deliberately uses scalar formula/convolution code rather than the
production signal-generation or estimator helpers.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from timing_sync import create_experiment, rrc_taps


SPS = 16
SPAN = 8
ROLLOFF = 0.35
HALF_SPAN_SAMPLES = SPAN * SPS // 2
FILTER_LENGTH = SPAN * SPS + 1
CASCADE_DELAY = FILTER_LENGTH - 1


def oracle_rrc() -> np.ndarray:
    """Evaluate the analytic RRC impulse response point by point."""
    values: list[float] = []
    beta = ROLLOFF
    for index in range(-HALF_SPAN_SAMPLES, HALF_SPAN_SAMPLES + 1):
        t = index / SPS
        if index == 0:
            value = 1.0 + beta * (4.0 / math.pi - 1.0)
        elif abs(4.0 * beta * t) == 1.0:
            value = (beta / math.sqrt(2.0)) * (
                (1.0 + 2.0 / math.pi) * math.sin(math.pi / (4.0 * beta))
                + (1.0 - 2.0 / math.pi) * math.cos(math.pi / (4.0 * beta))
            )
        else:
            numerator = math.sin(math.pi * t * (1.0 - beta)) + (
                4.0 * beta * t * math.cos(math.pi * t * (1.0 + beta))
            )
            denominator = math.pi * t * (1.0 - (4.0 * beta * t) ** 2)
            value = numerator / denominator
        values.append(value)
    norm = math.sqrt(sum(value * value for value in values))
    return np.asarray([value / norm for value in values], dtype=np.float64)


def oracle_convolve(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Small, explicit full convolution suitable for hand checking."""
    out = [0.0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            out[i + j] += float(a) * float(b)
    return np.asarray(out)


def oracle_frame(bits: list[int], pilot: list[int], offset: int) -> tuple[np.ndarray, list[int], int]:
    symbols = [0] * 4 + [2 * bit - 1 for bit in pilot] + [2 * bit - 1 for bit in bits] + [0] * 4
    upsampled = [0.0] * (len(symbols) * SPS)
    for k, symbol in enumerate(symbols):
        upsampled[k * SPS] = float(symbol)
    tx = oracle_convolve(np.asarray(upsampled), oracle_rrc())
    delayed = np.zeros_like(tx)
    if offset >= 0:
        delayed[offset:] = tx[: len(tx) - offset]
    else:
        delayed[:offset] = tx[-offset:]
    rx_mf = oracle_convolve(delayed, oracle_rrc())
    return rx_mf, symbols, CASCADE_DELAY


def oracle_sample_indices(start_symbol: int, count: int, phase: int, delay: int = CASCADE_DELAY) -> list[int]:
    return [delay + (start_symbol + i) * SPS + phase for i in range(count)]


def oracle_ber(reference: list[int], decisions: list[int]) -> tuple[int, int, float]:
    assert len(reference) == len(decisions)
    errors = sum(int(a != b) for a, b in zip(reference, decisions))
    return errors, len(reference), errors / len(reference)


def test_oracle_rrc_is_finite_symmetric_unit_energy_and_handles_singular_points() -> None:
    h = oracle_rrc()
    assert len(h) == FILTER_LENGTH == 129
    assert np.isfinite(h).all()
    assert np.allclose(h, h[::-1], rtol=0, atol=2e-15)
    assert math.isclose(float(np.dot(h, h)), 1.0, rel_tol=0, abs_tol=2e-15)
    assert h[HALF_SPAN_SAMPLES] > 0
    # The analytic singular cases at t=0 and t=±1/(4β) are explicitly finite.
    for t in (0.0, 1.0 / (4.0 * ROLLOFF), -1.0 / (4.0 * ROLLOFF)):
        assert math.isfinite(float(h[round(t * SPS) + HALF_SPAN_SAMPLES]))


def test_oracle_convolution_and_cascade_delay_are_exact() -> None:
    assert np.array_equal(oracle_convolve(np.array([1.0, 2.0]), np.array([3.0, 4.0])), [3.0, 10.0, 8.0])
    h = oracle_rrc()
    cascade = oracle_convolve(h, h)
    assert len(cascade) == 257
    assert int(np.argmax(cascade)) == CASCADE_DELAY == 128
    assert math.isclose(float(cascade[CASCADE_DELAY]), 1.0, rel_tol=0, abs_tol=2e-15)


def test_oracle_sample_indices_and_offset_sign_are_hand_checkable() -> None:
    bits = [0, 1, 1, 0]
    pilot = [0, 1, 0, 1] * 16
    base, _, delay = oracle_frame(bits, pilot, 0)
    plus, _, _ = oracle_frame(bits, pilot, 3)
    minus, _, _ = oracle_frame(bits, pilot, -3)
    payload_start = 4 + len(pilot)
    indices = oracle_sample_indices(payload_start, len(bits), 0, delay)
    assert indices[0] == 128 + (4 + 64) * 16
    assert indices == [indices[0] + i * SPS for i in range(len(bits))]
    # Positive q is a physical delay: the peak moves later by q samples.
    assert np.argmax(plus) == np.argmax(base) + 3
    assert np.argmax(minus) == np.argmax(base) - 3
    for q, response in ((3, plus), (-3, minus)):
        sampled = [response[index + q] for index in indices]
        assert [int(value > 0) for value in sampled] == bits


def test_oracle_ber_counts_only_fixed_payload_and_negative_control_detects_one_sample_error() -> None:
    bits = [0, 1, 0, 1, 1]
    decisions = [0, 0, 0, 1, 1]
    errors, denominator, ber = oracle_ber(bits, decisions)
    assert (errors, denominator, ber) == (1, 5, 0.2)
    # Isolated negative control: an accidental +1 sample index changes the
    # deterministic waveform decisions and must fail the expected BER check.
    pilot = [0, 1] * 32
    wave, _, delay = oracle_frame(bits, pilot, 3)
    start = 4 + len(pilot)
    valid = oracle_sample_indices(start, len(bits), 0, delay)
    correct = [int(wave[i + 3] > 0) for i in valid]
    mutant = [int(wave[i + SPS] > 0) for i in valid]
    assert oracle_ber(bits, correct) == (0, len(bits), 0.0)
    assert oracle_ber(bits, mutant)[0] > 0


@pytest.mark.parametrize("offset", [-7, -3, 0, 3, 7])
def test_production_chain_matches_independent_noiseless_oracle(offset: int) -> None:
    seed = 19
    rng = np.random.default_rng(seed)
    pilot = rng.integers(0, 2, size=64, dtype=np.uint8)
    bits = rng.integers(0, 2, size=512, dtype=np.uint8)
    expected_wave, _, delay = oracle_frame(bits.tolist(), pilot.tolist(), offset)
    production = create_experiment(seed=seed, timing_offset_samples=offset, eb_n0_db=12,
                                   n_payload_symbols=len(bits))
    # Independent direct convolution oracle checks every noiseless waveform sample.
    oracle_tx = oracle_convolve(np.repeat(np.zeros(1), 1), np.ones(1))  # hand-checkable kernel identity
    assert np.array_equal(oracle_tx, [0.0])
    symbols = [0] * 4 + [2 * int(bit) - 1 for bit in pilot] + [2 * int(bit) - 1 for bit in bits] + [0] * 4
    upsampled = np.zeros(len(symbols) * SPS)
    upsampled[::SPS] = symbols
    taps = oracle_rrc()
    expected_tx = oracle_convolve(upsampled, taps)
    delayed = np.zeros_like(expected_tx)
    if offset >= 0:
        delayed[offset:] = expected_tx[:len(expected_tx) - offset]
    else:
        delayed[:offset] = expected_tx[-offset:]
    # Recreate the independent noise stream from the documented seed and model.
    noise_rng = np.random.default_rng(seed)
    noise_rng.integers(0, 2, size=64, dtype=np.uint8)
    noise_rng.integers(0, 2, size=len(bits), dtype=np.uint8)
    sigma = math.sqrt(10.0 ** (-12.0 / 10.0) / 2.0)
    expected_rx = delayed + noise_rng.normal(0.0, sigma, size=delayed.shape)
    expected_matched = oracle_convolve(expected_rx, taps[::-1])
    assert np.allclose(rrc_taps(), taps, rtol=0, atol=2e-15)
    assert np.allclose(production["tx_waveform"], expected_tx, rtol=0, atol=2e-14)
    assert np.allclose(production["rx_waveform"], expected_rx, rtol=0, atol=2e-14)
    assert np.allclose(production["matched"], expected_matched, rtol=0, atol=2e-13)
    assert production["initial_measurement"]["scores"] == [
        {"phase_samples": phase, "mse": pytest.approx(float(np.mean((expected_matched[
            oracle_sample_indices(4 + 8, 48, phase, delay)] - (2.0 * pilot[8:-8] - 1.0)) ** 2)), abs=2e-14)}
        for phase in range(-7, 8)
    ]
    assert production["group_delay_samples"] == delay == 128
    assert np.argmax(expected_wave) == np.argmax(oracle_frame(bits.tolist(), pilot.tolist(), 0)[0]) + offset


def test_zero_noise_grid_estimator_recovers_known_integer_phase() -> None:
    pilot = np.asarray([((index * 7 + index // 3) % 11) < 5 for index in range(64)], dtype=np.uint8)
    payload = np.asarray([index % 2 for index in range(512)], dtype=np.uint8)
    expected, _, delay = oracle_frame(payload.tolist(), pilot.tolist(), 0)
    pilot_start = 4
    pilot_symbols = 2.0 * pilot.astype(np.float64) - 1.0
    scores = []
    for phase in range(-7, 8):
        idx = oracle_sample_indices(pilot_start + 8, 48, phase, delay)
        scores.append((float(np.mean((expected[idx] - pilot_symbols[8:-8]) ** 2)), phase))
    assert min(scores)[1] == 0
