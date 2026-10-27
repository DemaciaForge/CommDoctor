"""Stage13 pilot-trained LMS equalization over the Stage09 channel model."""
from __future__ import annotations

import math

import numpy as np

from multipath_equalization import (
    MAX_PAYLOAD_SYMBOLS,
    MIN_PAYLOAD_SYMBOLS,
    _symbol_samples,
    create_experiment as create_stage09_experiment,
)

TAPS = 5
MIN_TRAINING_SYMBOLS = 16
MAX_TRAINING_SYMBOLS = 60
MAX_MU = 0.5


def _integer(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def lms_step(weights: np.ndarray, window: np.ndarray, desired: float, mu: float) -> tuple[float, np.ndarray]:
    weights = np.asarray(weights, dtype=np.float64)
    window = np.asarray(window, dtype=np.float64)
    if weights.ndim != 1 or window.shape != weights.shape or not np.isfinite(weights).all() or not np.isfinite(window).all():
        raise ValueError("weights and window must be matching finite vectors")
    if isinstance(desired, bool) or not isinstance(desired, (int, float)) or not math.isfinite(float(desired)):
        raise ValueError("desired must be finite")
    if isinstance(mu, bool) or not isinstance(mu, (int, float)) or not math.isfinite(float(mu)) or not 0 < mu <= MAX_MU:
        raise ValueError(f"mu must be finite and in (0, {MAX_MU}]")
    output = float(weights @ window)
    error = float(desired) - output
    updated = weights + float(mu) * error * window
    if not math.isfinite(error) or not np.isfinite(updated).all():
        raise FloatingPointError("LMS update produced a non-finite value")
    return error, updated


def run_experiment(*, seed: int = 2026, eb_n0_db: float = 8.0,
                   n_training_symbols: int = 60, n_payload_symbols: int = 512,
                   mu: float = 0.01, path_delays_samples: list[int] | tuple[int, ...] = (0, 16),
                   path_gains: list[float] | tuple[float, ...] = (1.0, 0.7)) -> dict:
    seed = _integer(seed, "seed", 0, 2**32 - 1)
    training_n = _integer(n_training_symbols, "n_training_symbols", MIN_TRAINING_SYMBOLS, MAX_TRAINING_SYMBOLS)
    payload_n = _integer(n_payload_symbols, "n_payload_symbols", MIN_PAYLOAD_SYMBOLS, MAX_PAYLOAD_SYMBOLS)
    if isinstance(mu, bool) or not isinstance(mu, (int, float)) or not math.isfinite(float(mu)) or not 0 < mu <= MAX_MU:
        raise ValueError(f"mu must be finite and in (0, {MAX_MU}]")
    mu = float(mu)
    experiment = create_stage09_experiment(seed=seed, eb_n0_db=eb_n0_db,
        n_payload_symbols=training_n + payload_n, path_delays_samples=path_delays_samples,
        path_gains=path_gains)
    layout = experiment["layout"]
    matched_symbols = _symbol_samples(experiment["matched"], layout, 0,
                                     layout.payload_start_symbol + training_n + payload_n + 2)
    pilot_start = layout.pilot_start_symbol
    pilot = 2.0 * experiment["pilot_bits"].astype(np.float64) - 1.0
    payload = experiment["payload_bits"][training_n:]

    # A centered five-symbol window has fixed delay two: [k-2, ..., k+2].
    weights = np.zeros(TAPS, dtype=np.float64)
    history = []
    max_weight = 1e6
    diverged_at = None
    for k in range(2, training_n + 2):
        u = matched_symbols[pilot_start + k - 2:pilot_start + k + 3]
        desired = pilot[k]
        error, updated = lms_step(weights, u, float(desired), mu)
        history.append({"symbol": k, "mse": error * error})
        weights = updated
        if not np.isfinite(weights).all() or float(np.max(np.abs(weights))) > max_weight:
            diverged_at = k
            break

    if diverged_at is None:
        # The update after the final training row is the frozen evaluation vector.
        if not np.isfinite(weights).all():
            diverged_at = training_n - 3
    train_indices = list(range(2, training_n + 2))
    # Data generation places the training segment first in the existing payload.
    eval_indices = np.asarray(layout.payload_sample_indices[training_n:], dtype=np.int64)
    raw_indices = eval_indices
    raw_samples = experiment["matched"][raw_indices]
    raw_reference = payload
    equalized = []
    for index in eval_indices:
        symbol_index = int(round((int(index) - layout.group_delay_samples) / 16))
        u = matched_symbols[symbol_index - 2:symbol_index + 3]
        equalized.append(float(weights @ u))
    equalized = np.asarray(equalized, dtype=np.float64)
    raw_errors = int(np.count_nonzero((raw_samples > 0).astype(np.uint8) != raw_reference))
    eq_errors = int(np.count_nonzero((equalized > 0).astype(np.uint8) != raw_reference))
    converged = diverged_at is None and len(history) == len(train_indices) and np.isfinite(weights).all()
    mse_values = [row["mse"] for row in history]
    initial_mse = mse_values[0] if mse_values else float("inf")
    tail_n = max(1, len(mse_values) // 5)
    final_mse = float(np.mean(mse_values[-tail_n:])) if mse_values else float("inf")
    if diverged_at is not None:
        diagnosis = f"训练发散：符号索引 {diverged_at} 后系数超出数值边界；BER 仅作当前系数的有限样本测量。"
    elif final_mse > 1.5:
        diagnosis = "训练未显示稳定收敛：末段均方误差仍较高；请调整学习率或增加训练长度。"
    else:
        diagnosis = "训练过程数值稳定；末段误差仅描述本次训练序列，不保证所有信道和噪声下 BER 均改善。"
    return {
        "parameters": {"seed": seed, "eb_n0_db": float(eb_n0_db), "n_training_symbols": training_n,
                       "n_payload_symbols": payload_n, "mu": mu, "taps": TAPS,
                       "path_delays_samples": experiment["path_delays_samples"].tolist(),
                       "path_gains": experiment["path_gains"].tolist()},
        "contract": {"window_order": "oldest_to_newest", "window_symbols": TAPS,
                     "decision_delay_symbols": 2, "coefficient_initialization": "all_zeros",
                     "error": "desired - output", "update": "w_next = w + mu * error * u",
                     "training_indices": train_indices, "evaluation_indices": list(range(training_n, training_n + payload_n)),
                     "training_samples": len(train_indices), "same_channel_and_noise": True},
        "training": {"errors": history, "initial_mse": initial_mse, "final_mse": final_mse,
                     "converged": bool(converged), "diverged_at": diverged_at, "diagnosis": diagnosis,
                     "weights": weights.tolist()},
        "results": {
            "raw": {"errors": raw_errors, "compared": payload_n, "ber": raw_errors / payload_n},
            "lms": {"errors": eq_errors, "compared": payload_n, "ber": eq_errors / payload_n},
        },
        "series": {"training_mse": mse_values, "raw_samples": raw_samples.tolist(),
                   "equalized_samples": equalized.tolist()},
        "teaching": {"observation": f"本次 raw 为 {raw_errors}/{payload_n}，LMS 为 {eq_errors}/{payload_n}。",
                     "training": f"训练误差从首样本平方误差 {mse_values[0]:.4g} 到末段均方误差 {final_mse:.4g}。" if mse_values else "训练样本不足。",
                     "limitation": "评估 payload 未参与系数更新；BER 按同一接收帧中独立 payload 位统计。"}
    }
