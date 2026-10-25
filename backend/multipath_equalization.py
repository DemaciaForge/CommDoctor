"""Stage09 static multipath BPSK channel and training-aided equalization.

The module deliberately keeps the oversampled physical channel separate from the
Stage01--08 symbol-rate simulators.  All arrays are generated once per
experiment and the equalizers only consume the cached matched-filter samples.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from timing_sync import rrc_taps

SAMPLES_PER_SYMBOL = 16
ROLLOFF = 0.35
SPAN_SYMBOLS = 8
PILOT_SYMBOLS = 64
FRAME_GUARD_SYMBOLS = 4
EQUALIZER_TAPS = 5
MIN_PAYLOAD_SYMBOLS = 128
MAX_PAYLOAD_SYMBOLS = 4096
MIN_EB_N0_DB = 0.0
MAX_EB_N0_DB = 20.0
MAX_PATHS = 3
MAX_DELAY_SYMBOLS = 8


@dataclass(frozen=True)
class FrameLayout:
    pilot_start_symbol: int
    pilot_length: int
    payload_start_symbol: int
    payload_length: int
    guard_symbols: int
    tx_filter_delay: int
    rx_filter_delay: int
    channel_reference_delay: int
    payload_sample_indices: tuple[int, ...]

    @property
    def group_delay_samples(self) -> int:
        return self.tx_filter_delay + self.rx_filter_delay + self.channel_reference_delay


def _strict_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def validate_channel(path_delays_samples: object, path_gains: object) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(path_delays_samples, (list, tuple)) or not isinstance(path_gains, (list, tuple)):
        raise ValueError("path_delays_samples and path_gains must be arrays")
    if not 1 <= len(path_delays_samples) <= MAX_PATHS or len(path_delays_samples) != len(path_gains):
        raise ValueError(f"channel must contain 1 through {MAX_PATHS} paths with matching lengths")
    delays = np.asarray([_strict_int(v, "path delay") for v in path_delays_samples], dtype=np.int64)
    gains_values: list[float] = []
    for value in path_gains:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("path gains must be finite real numbers")
        gains_values.append(float(value))
    gains = np.asarray(gains_values, dtype=np.float64)
    if np.any(delays < 0) or np.any(delays > MAX_DELAY_SYMBOLS * SAMPLES_PER_SYMBOL):
        raise ValueError("path delays must be non-negative and at most 8 symbols")
    if np.any(delays % SAMPLES_PER_SYMBOL != 0):
        raise ValueError("MVP path delays must be integer symbol delays (multiples of 16 samples)")
    if len(set(delays.tolist())) != len(delays):
        raise ValueError("path delays must be unique")
    if not np.any(np.abs(gains) > 0):
        raise ValueError("at least one path gain must be non-zero")
    order = np.argsort(delays)
    return delays[order], gains[order]


def _validate_common(seed: object, eb_n0_db: object, n_payload_symbols: object) -> tuple[int, float, int]:
    seed_i = _strict_int(seed, "seed")
    if not 0 <= seed_i <= 2**32 - 1:
        raise ValueError("seed must be between 0 and 2^32-1")
    if isinstance(eb_n0_db, bool) or not isinstance(eb_n0_db, (int, float)) or not math.isfinite(float(eb_n0_db)):
        raise ValueError("eb_n0_db must be a finite real number")
    snr = float(eb_n0_db)
    if not MIN_EB_N0_DB <= snr <= MAX_EB_N0_DB:
        raise ValueError(f"eb_n0_db must be between {MIN_EB_N0_DB} and {MAX_EB_N0_DB}")
    payload_n = _strict_int(n_payload_symbols, "n_payload_symbols")
    if not MIN_PAYLOAD_SYMBOLS <= payload_n <= MAX_PAYLOAD_SYMBOLS:
        raise ValueError(f"n_payload_symbols must be between {MIN_PAYLOAD_SYMBOLS} and {MAX_PAYLOAD_SYMBOLS}")
    return seed_i, snr, payload_n


def full_convolve(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Explicit full convolution used by the production channel (and oracle tests)."""
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.ndim != 1 or b.ndim != 1 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("convolution inputs must be finite one-dimensional arrays")
    return np.convolve(a, b, mode="full")


def _channel_output(tx: np.ndarray, delays: np.ndarray, gains: np.ndarray) -> np.ndarray:
    output = np.zeros(len(tx) + int(delays.max()), dtype=np.float64)
    norm = float(np.linalg.norm(gains))
    normalized = gains / norm
    for delay, gain in zip(delays, normalized):
        start = int(delay)
        output[start : start + len(tx)] += float(gain) * tx
    return output


def _symbols_from_bits(bits: np.ndarray) -> np.ndarray:
    return 2.0 * bits.astype(np.float64) - 1.0


def _layout(payload_length: int, channel_reference_delay: int) -> FrameLayout:
    payload_start = FRAME_GUARD_SYMBOLS + PILOT_SYMBOLS
    total_symbols = FRAME_GUARD_SYMBOLS + PILOT_SYMBOLS + payload_length + FRAME_GUARD_SYMBOLS
    delay = len(rrc_taps()) - 1
    indices = tuple(delay + channel_reference_delay + (payload_start + np.arange(payload_length)) * SAMPLES_PER_SYMBOL)
    # The final matched-filter samples include the complete channel and RRC tails.
    if indices[-1] >= total_symbols * SAMPLES_PER_SYMBOL + 2 * delay + channel_reference_delay:
        raise ValueError("payload index exceeds matched-filter output")
    return FrameLayout(FRAME_GUARD_SYMBOLS, PILOT_SYMBOLS, payload_start, payload_length,
                       FRAME_GUARD_SYMBOLS, delay // 2, delay // 2, channel_reference_delay, indices)


def _symbol_samples(matched: np.ndarray, layout: FrameLayout, start: int, count: int) -> np.ndarray:
    indices = layout.group_delay_samples + start * SAMPLES_PER_SYMBOL + np.arange(count) * SAMPLES_PER_SYMBOL
    if indices[0] < 0 or indices[-1] >= len(matched):
        raise ValueError("symbol sample index is outside matched-filter output")
    values = matched[indices]
    if not np.isfinite(values).all():
        raise ValueError("matched-filter samples must be finite")
    return values


def _pilot_regression(matched: np.ndarray, pilot_symbols: np.ndarray, layout: FrameLayout) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # Guard symbols provide the two known boundary samples around the pilot.
    symbol_values = _symbol_samples(matched, layout, layout.pilot_start_symbol - 2, PILOT_SYMBOLS + 4)
    rows = []
    targets = []
    # Only the 60 pilot centers with a complete 5-symbol window are used.
    # Rows are centered on the target symbol; the known 4-symbol frame guards
    # make the payload-side receive windows complete without dropping payload.
    for pilot_index in range(2, PILOT_SYMBOLS - 2):
        row_start = pilot_index
        rows.append(symbol_values[row_start:row_start + EQUALIZER_TAPS])
        targets.append(float(pilot_symbols[pilot_index]))
    return np.asarray(rows), np.asarray(targets), symbol_values


def fit_equalizer(matched: np.ndarray, pilot_bits: np.ndarray, layout: FrameLayout, *, algorithm: str, noise_variance: float) -> dict:
    if algorithm not in {"zf", "mmse"}:
        raise ValueError("algorithm must be zf or mmse")
    pilot_symbols = _symbols_from_bits(pilot_bits)
    X, target, _ = _pilot_regression(matched, pilot_symbols, layout)
    gram = X.T @ X
    regularization = float(noise_variance) if algorithm == "mmse" else 0.0
    matrix = gram + regularization * np.eye(EQUALIZER_TAPS)
    try:
        taps = np.linalg.solve(matrix, X.T @ target)
    except np.linalg.LinAlgError:
        taps = np.linalg.pinv(matrix) @ X.T @ target
    cond = float(np.linalg.cond(gram)) if np.all(np.isfinite(gram)) else float("inf")
    return {"taps": taps, "condition_number": cond, "regularization": regularization,
            "training_rows": int(len(X)), "training_residual_rms": float(np.sqrt(np.mean((X @ taps - target) ** 2)))}


def _ber(reference_bits: np.ndarray, decisions: np.ndarray, layout: FrameLayout, algorithm: str = "raw") -> dict:
    errors = int(np.count_nonzero(reference_bits != decisions))
    n = int(len(reference_bits))
    if n <= 0:
        raise ValueError("cannot compute BER with zero valid payload samples")
    return {"algorithm": algorithm, "n_errors": errors, "n_compared": n, "ber": errors / n,
            "payload_symbol_start": layout.payload_start_symbol,
            "payload_symbol_end_exclusive": layout.payload_start_symbol + layout.payload_length,
            "sample_indices": [int(v) for v in layout.payload_sample_indices], "decision_delay_symbols": 0}


def create_experiment(*, seed: int, eb_n0_db: float, n_payload_symbols: int,
                      path_delays_samples: list[int] | tuple[int, ...] = (0, 16),
                      path_gains: list[float] | tuple[float, ...] = (1.0, 0.7)) -> dict:
    seed_i, snr, payload_n = _validate_common(seed, eb_n0_db, n_payload_symbols)
    delays, gains = validate_channel(path_delays_samples, path_gains)
    rng = np.random.default_rng(seed_i)
    pilot_bits = rng.integers(0, 2, size=PILOT_SYMBOLS, dtype=np.uint8)
    payload_bits = rng.integers(0, 2, size=payload_n, dtype=np.uint8)
    frame_bits = np.concatenate((np.zeros(FRAME_GUARD_SYMBOLS, dtype=np.uint8), pilot_bits, payload_bits,
                                 np.zeros(FRAME_GUARD_SYMBOLS, dtype=np.uint8)))
    frame_symbols = _symbols_from_bits(frame_bits)
    frame_symbols[:FRAME_GUARD_SYMBOLS] = 0.0
    frame_symbols[-FRAME_GUARD_SYMBOLS:] = 0.0
    upsampled = np.zeros(len(frame_symbols) * SAMPLES_PER_SYMBOL, dtype=np.float64)
    upsampled[::SAMPLES_PER_SYMBOL] = frame_symbols
    taps = rrc_taps()
    transmitted = full_convolve(upsampled, taps)
    channel = _channel_output(transmitted, delays, gains)
    noise_variance = 10.0 ** (-snr / 10.0) / 2.0
    received = channel + rng.normal(0.0, math.sqrt(noise_variance), size=len(channel))
    matched = full_convolve(received, taps[::-1])
    layout = _layout(payload_n, int(delays[0]))
    raw_samples = _symbol_samples(matched, layout, layout.payload_start_symbol, payload_n)
    raw = _ber(payload_bits, (raw_samples > 0).astype(np.uint8), layout)
    preview_indices = np.arange(0, min(len(transmitted), 512), dtype=np.int64)
    channel_impulse = np.zeros(int(delays.max()) + 1, dtype=np.float64)
    channel_impulse[delays] = gains / np.linalg.norm(gains)
    return {"seed": seed_i, "eb_n0_db": snr, "n_payload_symbols": payload_n,
            "path_delays_samples": delays, "path_gains": gains / np.linalg.norm(gains),
            "pilot_bits": pilot_bits, "payload_bits": payload_bits, "frame_symbols": frame_symbols,
            "tx_waveform": transmitted, "channel_waveform": channel, "rx_waveform": received,
            "matched": matched, "rrc_taps": taps, "noise_variance": noise_variance,
            "layout": layout, "channel_impulse": channel_impulse, "raw_ber": raw,
            "preview_indices": preview_indices}


def estimate_channel(experiment: dict) -> dict:
    fit = fit_equalizer(experiment["matched"], experiment["pilot_bits"], experiment["layout"],
                        algorithm="mmse", noise_variance=experiment["noise_variance"])
    experiment["measurement"] = fit
    return {"status": "estimated", "estimated_taps": fit["taps"].tolist(),
            "condition_number": fit["condition_number"], "training_rows": fit["training_rows"],
            "training_residual_rms": fit["training_residual_rms"],
            "regularization": fit["regularization"], "payload_sample_indices": [int(v) for v in experiment["layout"].payload_sample_indices]}


def equalize(experiment: dict, algorithm: str) -> dict:
    if "measurement" not in experiment:
        estimate_channel(experiment)
    fit = fit_equalizer(experiment["matched"], experiment["pilot_bits"], experiment["layout"],
                        algorithm=algorithm, noise_variance=experiment["noise_variance"])
    layout: FrameLayout = experiment["layout"]
    # Apply the fitted row convention directly: each decision is the dot
    # product of [y[k-2], ..., y[k+2]].  Using np.convolve here would reverse
    # the taps and silently change the declared decision delay.
    all_samples = _symbol_samples(experiment["matched"], layout,
                                  layout.payload_start_symbol - 2,
                                  layout.payload_length + 4)
    windows = np.asarray([all_samples[index:index + EQUALIZER_TAPS]
                          for index in range(layout.payload_length)])
    decisions = (windows @ fit["taps"] > 0).astype(np.uint8)
    result = _ber(experiment["payload_bits"], decisions, layout, algorithm)
    result.update({"equalizer_taps": fit["taps"].tolist(), "condition_number": fit["condition_number"],
                   "regularization": fit["regularization"], "training_residual_rms": fit["training_residual_rms"],
                   "improved_vs_raw": result["n_errors"] < experiment["raw_ber"]["n_errors"]})
    experiment.setdefault("equalizations", {})[algorithm] = result
    return result
