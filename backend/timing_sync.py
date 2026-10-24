"""Isolated oversampled BPSK timing-offset teaching model for Stage08."""

from __future__ import annotations

import math

import numpy as np

SAMPLES_PER_SYMBOL = 16
ROLLOFF = 0.35
SPAN_SYMBOLS = 8
PILOT_SYMBOLS = 64
PILOT_GUARD_SYMBOLS = 8
FRAME_GUARD_SYMBOLS = 4
TIMING_PHASES = tuple(range(-7, 8))
MIN_PAYLOAD_SYMBOLS = 512
MAX_PAYLOAD_SYMBOLS = 4096
MIN_EB_N0_DB = 0.0
MAX_EB_N0_DB = 12.0


def rrc_taps(rolloff: float = ROLLOFF, span_symbols: int = SPAN_SYMBOLS,
             samples_per_symbol: int = SAMPLES_PER_SYMBOL) -> np.ndarray:
    """Return unit-energy, symmetric root-raised-cosine FIR taps."""
    if isinstance(rolloff, bool) or not isinstance(rolloff, (int, float)) or not math.isfinite(rolloff) or not 0 < rolloff <= 1:
        raise ValueError("rolloff must be finite and in (0, 1]")
    if isinstance(span_symbols, bool) or not isinstance(span_symbols, int) or span_symbols <= 0 or span_symbols % 2:
        raise ValueError("span_symbols must be a positive even integer")
    if isinstance(samples_per_symbol, bool) or not isinstance(samples_per_symbol, int) or samples_per_symbol < 2:
        raise ValueError("samples_per_symbol must be an integer of at least 2")
    half = span_symbols * samples_per_symbol // 2
    t = np.arange(-half, half + 1, dtype=np.float64) / samples_per_symbol
    h = np.empty_like(t)
    for i, ti in enumerate(t):
        if abs(ti) < 1e-14:
            h[i] = 1.0 + rolloff * (4.0 / math.pi - 1.0)
        elif abs(abs(4.0 * rolloff * ti) - 1.0) < 1e-12:
            h[i] = (rolloff / math.sqrt(2.0)) * (
                (1.0 + 2.0 / math.pi) * math.sin(math.pi / (4.0 * rolloff))
                + (1.0 - 2.0 / math.pi) * math.cos(math.pi / (4.0 * rolloff))
            )
        else:
            numerator = math.sin(math.pi * ti * (1.0 - rolloff)) + 4.0 * rolloff * ti * math.cos(math.pi * ti * (1.0 + rolloff))
            denominator = math.pi * ti * (1.0 - (4.0 * rolloff * ti) ** 2)
            h[i] = numerator / denominator
    h /= math.sqrt(float(np.dot(h, h)))
    return h


def _delay(samples: np.ndarray, offset_samples: int) -> np.ndarray:
    delayed = np.zeros_like(samples)
    if offset_samples >= 0:
        delayed[offset_samples:] = samples[: len(samples) - offset_samples]
    else:
        delayed[:offset_samples] = samples[-offset_samples:]
    return delayed


def _sample_indices(symbol_start: int, count: int, phase_samples: int, delay_samples: int,
                    samples_per_symbol: int = SAMPLES_PER_SYMBOL) -> np.ndarray:
    indices = delay_samples + (symbol_start + np.arange(count, dtype=np.int64)) * samples_per_symbol + phase_samples
    return indices


def sample_symbols(matched: np.ndarray, symbol_start: int, count: int, phase_samples: int,
                   delay_samples: int) -> np.ndarray:
    if not isinstance(matched, np.ndarray) or matched.ndim != 1 or not np.issubdtype(matched.dtype, np.number):
        raise ValueError("matched must be a one-dimensional numeric array")
    if isinstance(phase_samples, bool) or not isinstance(phase_samples, int) or phase_samples not in TIMING_PHASES:
        raise ValueError("phase_samples must be an integer from -7 through 7")
    if isinstance(symbol_start, bool) or not isinstance(symbol_start, int) or symbol_start < 0:
        raise ValueError("symbol_start must be a non-negative integer")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("count must be a positive integer")
    indices = _sample_indices(symbol_start, count, phase_samples, delay_samples)
    if indices[0] < 0 or indices[-1] >= len(matched):
        raise ValueError("requested symbol samples fall outside the valid matched-filter output")
    values = matched[indices]
    if not np.isfinite(values).all():
        raise ValueError("matched samples must be finite")
    return values


def estimate_timing(matched: np.ndarray, pilot_bits: np.ndarray, pilot_start: int,
                    delay_samples: int) -> dict:
    if not isinstance(pilot_bits, np.ndarray) or pilot_bits.ndim != 1 or len(pilot_bits) != PILOT_SYMBOLS:
        raise ValueError("pilot_bits must contain exactly 64 bits")
    if not np.isin(pilot_bits, [0, 1]).all():
        raise ValueError("pilot_bits must contain only 0 and 1")
    pilot_symbols = 2.0 * pilot_bits.astype(np.float64) - 1.0
    start = pilot_start + PILOT_GUARD_SYMBOLS
    count = PILOT_SYMBOLS - 2 * PILOT_GUARD_SYMBOLS
    scores = []
    for phase in TIMING_PHASES:
        observed = sample_symbols(matched, start, count, phase, delay_samples)
        mse = float(np.mean((observed - pilot_symbols[PILOT_GUARD_SYMBOLS:-PILOT_GUARD_SYMBOLS]) ** 2))
        scores.append({"phase_samples": phase, "mse": mse})
    best = min(scores, key=lambda item: (item["mse"], abs(item["phase_samples"]), item["phase_samples"]))
    return {"phase_samples": best["phase_samples"], "scores": scores, "pilot_start_symbol": start,
            "pilot_symbols_used": count}


def ber_for_phase(matched: np.ndarray, payload_bits: np.ndarray, payload_start: int,
                  phase_samples: int, delay_samples: int) -> dict:
    if not isinstance(payload_bits, np.ndarray) or payload_bits.ndim != 1 or len(payload_bits) == 0:
        raise ValueError("payload_bits must be a non-empty one-dimensional array")
    if not np.isin(payload_bits, [0, 1]).all():
        raise ValueError("payload_bits must contain only 0 and 1")
    observed = sample_symbols(matched, payload_start, len(payload_bits), phase_samples, delay_samples)
    decisions = (observed > 0.0).astype(np.uint8)
    errors = int(np.count_nonzero(decisions != payload_bits))
    return {"phase_samples": phase_samples, "n_errors": errors, "n_compared": int(len(payload_bits)),
            "ber": errors / int(len(payload_bits)),
            "payload_symbol_start": payload_start, "payload_symbol_end_exclusive": payload_start + len(payload_bits)}


def create_experiment(*, seed: int, timing_offset_samples: int, eb_n0_db: float,
                      n_payload_symbols: int) -> dict:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer from 0 through 2^32-1")
    if isinstance(timing_offset_samples, bool) or not isinstance(timing_offset_samples, int) or timing_offset_samples not in TIMING_PHASES:
        raise ValueError("timing_offset_samples must be an integer from -7 through 7")
    if isinstance(eb_n0_db, bool) or not isinstance(eb_n0_db, (int, float)) or not math.isfinite(eb_n0_db) or not MIN_EB_N0_DB <= eb_n0_db <= MAX_EB_N0_DB:
        raise ValueError("eb_n0_db must be finite and between 0 and 12")
    if isinstance(n_payload_symbols, bool) or not isinstance(n_payload_symbols, int) or not MIN_PAYLOAD_SYMBOLS <= n_payload_symbols <= MAX_PAYLOAD_SYMBOLS:
        raise ValueError("n_payload_symbols must be an integer from 512 through 4096")

    rng = np.random.default_rng(seed)
    pilot_bits = rng.integers(0, 2, size=PILOT_SYMBOLS, dtype=np.uint8)
    payload_bits = rng.integers(0, 2, size=n_payload_symbols, dtype=np.uint8)
    all_bits = np.concatenate((np.zeros(FRAME_GUARD_SYMBOLS, dtype=np.uint8), pilot_bits, payload_bits,
                               np.zeros(FRAME_GUARD_SYMBOLS, dtype=np.uint8)))
    symbols = 2.0 * all_bits.astype(np.float64) - 1.0
    symbols[:FRAME_GUARD_SYMBOLS] = 0.0
    symbols[-FRAME_GUARD_SYMBOLS:] = 0.0
    upsampled = np.zeros(len(symbols) * SAMPLES_PER_SYMBOL, dtype=np.float64)
    upsampled[::SAMPLES_PER_SYMBOL] = symbols
    taps = rrc_taps()
    transmitted = np.convolve(upsampled, taps, mode="full")
    delayed = _delay(transmitted, timing_offset_samples)
    n0 = 10.0 ** (-float(eb_n0_db) / 10.0)
    noise_std = math.sqrt(n0 / 2.0)
    received = delayed + rng.normal(0.0, noise_std, size=delayed.shape)
    matched = np.convolve(received, taps[::-1], mode="full")
    group_delay = len(taps) - 1
    pilot_start = FRAME_GUARD_SYMBOLS
    payload_start = pilot_start + PILOT_SYMBOLS
    before = ber_for_phase(matched, payload_bits, payload_start, 0, group_delay)
    estimate = estimate_timing(matched, pilot_bits, pilot_start, group_delay)

    # Keep the browser payload bounded and expose no payload bits or hidden truth.
    preview_end = min(len(matched), group_delay + (pilot_start + 20) * SAMPLES_PER_SYMBOL)
    preview_start = max(0, group_delay + (pilot_start - 2) * SAMPLES_PER_SYMBOL)
    indices = np.arange(preview_start, preview_end, dtype=np.int64)
    return {"seed": seed, "timing_offset_samples": timing_offset_samples, "eb_n0_db": float(eb_n0_db),
            "n_payload_symbols": n_payload_symbols, "pilot_bits": pilot_bits, "payload_bits": payload_bits,
            "tx_waveform": transmitted, "rx_waveform": received, "matched": matched, "taps": taps,
            "group_delay_samples": group_delay, "pilot_start_symbol": pilot_start,
            "payload_start_symbol": payload_start, "initial_ber": before, "initial_measurement": estimate,
            "preview": {"sample_indices": indices, "time_symbols": indices / SAMPLES_PER_SYMBOL,
                        "tx": transmitted[np.clip(indices, 0, len(transmitted) - 1)],
                        "matched": matched[indices]}}
