"""Unified complex-baseband BPSK experiments for the Stage05 challenge."""

from __future__ import annotations

import math

import numpy as np

from frequency_offset import (
    MAX_UNAMBIGUOUS_OFFSET,
    calculate_bpsk_ber,
    compensate_bpsk_frequency_offset,
    estimate_bpsk_frequency_offset,
)


FAULT_SCENARIOS = ("none", "dc_offset", "frequency_offset", "both")
DC_MAGNITUDE = 0.35
FREQUENCY_MAGNITUDE = 0.02


def simulate_multi_fault(
    *, seed: int, scenario: str, dc_offset: float, epsilon: float,
    n_symbols: int = 4096, eb_n0_db: float = 8.0,
) -> dict:
    """Generate r[n] = a[n] exp(j 2 pi epsilon n) + dc_offset + w[n]."""
    if scenario not in FAULT_SCENARIOS:
        raise ValueError("unknown Stage05 fault scenario")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if isinstance(n_symbols, bool) or not isinstance(n_symbols, int) or n_symbols < 128:
        raise ValueError("n_symbols must be an integer of at least 128")
    for name, value in (("dc_offset", dc_offset), ("epsilon", epsilon), ("eb_n0_db", eb_n0_db)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite real number")
    if abs(epsilon) >= MAX_UNAMBIGUOUS_OFFSET:
        raise ValueError("abs(epsilon) must be less than 0.25 cycles per symbol")

    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=n_symbols, dtype=np.int8)
    symbols = (2 * bits - 1).astype(np.float64)
    n = np.arange(n_symbols, dtype=np.float64)
    sigma_iq = math.sqrt(0.5 * 10.0 ** (-float(eb_n0_db) / 10.0))
    noise = sigma_iq * (rng.standard_normal(n_symbols) + 1j * rng.standard_normal(n_symbols))
    clean = symbols * np.exp(1j * 2.0 * np.pi * float(epsilon) * n)
    received = clean + float(dc_offset) + noise
    before = calculate_bpsk_ber(bits, received)
    return {
        "bits": bits, "symbols": symbols, "noise": noise, "received": received,
        "n_symbols": n_symbols, "eb_n0_db": float(eb_n0_db), "sigma_iq": sigma_iq,
        "ber_theoretical": float(0.5 * math.erfc(math.sqrt(10.0 ** (float(eb_n0_db) / 10.0)))),
        "before": before,
    }


def estimate_dc_offset(received: np.ndarray) -> float:
    """Estimate real receive-path DC from the observed I-channel mean."""
    values = np.asarray(received)
    if values.ndim != 1 or values.size < 2 or values.dtype.kind not in "fc":
        raise ValueError("received must be a one-dimensional complex signal")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("received must contain only finite complex samples")
    result = float(np.mean(values.real))
    if not math.isfinite(result):
        raise ValueError("DC estimate is not finite")
    return result


def estimate_multi_fault(received: np.ndarray) -> dict:
    """Measure DC first, then estimate frequency on the DC-corrected samples."""
    dc_hat = estimate_dc_offset(received)
    dc_corrected = np.asarray(received) - dc_hat
    epsilon_hat = estimate_bpsk_frequency_offset(dc_corrected)
    return {"dc_hat": dc_hat, "epsilon_hat": epsilon_hat, "dc_corrected": dc_corrected}


def apply_compensation(received: np.ndarray, dc_hat: float, epsilon_hat: float, mode: str) -> np.ndarray:
    """Apply exactly the requested Stage05 processing path to the same samples."""
    if mode not in ("dc", "frequency", "both"):
        raise ValueError("mode must be dc, frequency, or both")
    values = np.asarray(received)
    if values.ndim != 1 or values.dtype.kind not in "fc" or not np.all(np.isfinite(values)):
        raise ValueError("received must be a finite one-dimensional complex signal")
    if isinstance(dc_hat, bool) or not isinstance(dc_hat, (int, float)) or not math.isfinite(dc_hat):
        raise ValueError("dc_hat must be a finite real number")
    if isinstance(epsilon_hat, bool) or not isinstance(epsilon_hat, (int, float)) or not math.isfinite(epsilon_hat):
        raise ValueError("epsilon_hat must be a finite real number")
    if abs(epsilon_hat) >= MAX_UNAMBIGUOUS_OFFSET:
        raise ValueError("abs(epsilon_hat) must be less than 0.25 cycles per symbol")
    corrected = values
    if mode in ("dc", "both"):
        corrected = corrected - float(dc_hat)
    if mode in ("frequency", "both"):
        corrected = compensate_bpsk_frequency_offset(corrected, float(epsilon_hat))
    return corrected
