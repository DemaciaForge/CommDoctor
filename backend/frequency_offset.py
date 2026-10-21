"""Complex-baseband BPSK frequency-offset simulation, estimation, and correction."""

from __future__ import annotations

import math

import numpy as np
from scipy.special import erfc


MAX_UNAMBIGUOUS_OFFSET = 0.25  # cycles per symbol, from the squared-BPSK estimator


def simulate_bpsk_frequency_offset(
    *, seed: int, n_symbols: int = 2048, eb_n0_db: float = 8.0, epsilon: float
) -> dict:
    """Generate r[n] = a[n] exp(j 2 pi epsilon n) + w[n].

    Eb=1 and each complex-noise component has variance N0/2=1/(2*Eb/N0).
    """
    if isinstance(n_symbols, bool) or not isinstance(n_symbols, int) or n_symbols < 128:
        raise ValueError("n_symbols must be an integer of at least 128")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if isinstance(epsilon, bool) or not isinstance(epsilon, (int, float)) or not math.isfinite(epsilon):
        raise ValueError("epsilon must be a finite real number")
    if abs(epsilon) >= MAX_UNAMBIGUOUS_OFFSET:
        raise ValueError("abs(epsilon) must be less than 0.25 cycles per symbol")
    if isinstance(eb_n0_db, bool) or not isinstance(eb_n0_db, (int, float)) or not math.isfinite(eb_n0_db):
        raise ValueError("eb_n0_db must be a finite real number")

    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=n_symbols, dtype=np.int8)
    symbols = (2 * bits - 1).astype(np.float64)
    n = np.arange(n_symbols, dtype=np.float64)
    phase = 2.0 * np.pi * float(epsilon) * n
    sigma_iq = math.sqrt(0.5 * 10.0 ** (-float(eb_n0_db) / 10.0))
    noise = sigma_iq * (rng.standard_normal(n_symbols) + 1j * rng.standard_normal(n_symbols))
    received = symbols * np.exp(1j * phase) + noise
    hard_bits = (received.real > 0).astype(np.int8)
    errors = int(np.count_nonzero(hard_bits != bits))
    return {
        "bits": bits,
        "symbols": symbols,
        "received": received,
        "noise": noise,
        "phase_rad": phase,
        "sigma_iq": sigma_iq,
        "n_errors": errors,
        "ber": errors / n_symbols,
        "ber_theoretical": float(0.5 * erfc(math.sqrt(10.0 ** (float(eb_n0_db) / 10.0)))),
    }


def estimate_bpsk_frequency_offset(received: np.ndarray) -> float:
    """Estimate cycles/symbol from the spectral peak of squared BPSK samples.

    Squaring removes the BPSK data symbols and doubles the carrier rotation.
    Zero padding refines the FFT peak enough to avoid a long residual phase
    ramp when the estimate is used to derotate a finite packet.
    """
    values = np.asarray(received)
    if values.ndim != 1 or values.size < 2 or values.dtype.kind not in "fc":
        raise ValueError("received must be a one-dimensional complex signal with at least two samples")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("received must contain only finite complex samples")
    squared = values * values
    if not np.any(squared):
        raise ValueError("frequency offset cannot be estimated from this signal")
    # The squared carrier has normalized frequency 2*epsilon in (-0.5, 0.5).
    # A 16x zero-padded FFT interpolates the peak to 1/(32N) cycles/symbol.
    fft_size = 16 * values.size
    spectrum = np.fft.fft(squared, n=fft_size)
    peak = int(np.argmax(np.abs(spectrum)))
    frequency = float(np.fft.fftfreq(fft_size)[peak])
    return frequency / 2.0


def compensate_bpsk_frequency_offset(received: np.ndarray, epsilon_hat: float) -> np.ndarray:
    """Rotate by the opposite estimated phase progression."""
    values = np.asarray(received)
    if values.ndim != 1 or values.size == 0 or values.dtype.kind not in "fc":
        raise ValueError("received must be a non-empty one-dimensional complex signal")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("received must contain only finite complex samples")
    if isinstance(epsilon_hat, bool) or not isinstance(epsilon_hat, (int, float)) or not math.isfinite(epsilon_hat):
        raise ValueError("epsilon_hat must be a finite real number")
    if abs(epsilon_hat) >= MAX_UNAMBIGUOUS_OFFSET:
        raise ValueError("abs(epsilon_hat) must be less than 0.25 cycles per symbol")
    n = np.arange(values.size, dtype=np.float64)
    return values * np.exp(-1j * 2.0 * np.pi * float(epsilon_hat) * n)


def calculate_bpsk_ber(bits: np.ndarray, received: np.ndarray) -> dict:
    bits_array = np.asarray(bits)
    values = np.asarray(received)
    if bits_array.ndim != 1 or bits_array.size == 0 or bits_array.dtype.kind not in "biu":
        raise ValueError("bits must be a non-empty one-dimensional binary array")
    if not np.all((bits_array == 0) | (bits_array == 1)):
        raise ValueError("bits must contain only zero and one")
    if values.ndim != 1 or values.size != bits_array.size or values.dtype.kind not in "fc":
        raise ValueError("received must be a complex signal aligned with bits")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("received must contain only finite complex samples")
    errors = int(np.count_nonzero((values.real > 0).astype(np.int8) != bits_array))
    return {"n_errors": errors, "ber": errors / int(bits_array.size)}


def phase_track(received: np.ndarray, count: int = 256) -> list[float]:
    """BPSK data-aided phase trajectory from unwrap(angle(r[n]^2))/2."""
    values = np.asarray(received)
    squared_phase = np.unwrap(np.angle(values[:count] ** 2)) / 2.0
    return [float(value) for value in squared_phase]
