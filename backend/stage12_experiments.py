"""Bounded, reproducible Stage12 hard/soft Viterbi comparison experiments."""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal, InvalidOperation

import numpy as np

from convolutional_coding import (
    CODE_RATE,
    CONSTRAINT_LENGTH,
    EB_INFO,
    MAX_SWEEP_INFORMATION_BITS,
    MAX_SWEEP_POINTS,
    MAX_SWEEP_TOTAL_INFORMATION_BITS,
    TAIL_BITS,
    ber,
    encode_frame,
    hard_decision,
    snr_quantities,
)
from stage12_soft_viterbi import paired_decode


MAX_COMPARE_INFORMATION_BITS = 4096
MAX_DETAIL_INFORMATION_BITS = 256
_PAYLOAD_TAG = 0x53543132
_NOISE_TAG = 0x4E4F4953


def _seed(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= int(value) <= 2**32 - 1:
        raise ValueError("seed must be an integer in [0, 2**32-1]")
    return int(value)


def _information_length(value: int, *, maximum: int = MAX_COMPARE_INFORMATION_BITS) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 1 <= int(value) <= maximum:
        raise ValueError(f"n_information_bits must be an integer in [1, {maximum}]")
    return int(value)


def _float(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(f"{name} must be a finite real number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return value


def _payload(seed: int, n: int) -> tuple[int, ...]:
    stream = np.random.default_rng(np.random.SeedSequence([seed, _PAYLOAD_TAG]))
    return tuple(int(bit) for bit in stream.integers(0, 2, size=n))


def _point_seed(seed: int, index: int) -> int:
    return int(np.random.SeedSequence([seed, index, _NOISE_TAG]).generate_state(1, dtype=np.uint32)[0])


def _digest(values: tuple[float, ...] | tuple[int, ...]) -> str:
    array = np.asarray(values)
    if array.dtype.kind in "iu":
        payload = bytes(int(value) for value in values)
    else:
        payload = np.asarray(values, dtype="<f8").tobytes()
    return hashlib.sha256(payload).hexdigest()


def scan_points(start_db: float, stop_db: float, step_db: float) -> tuple[float, ...]:
    values: list[Decimal] = []
    for name, value in (("start_db", start_db), ("stop_db", stop_db), ("step_db", step_db)):
        value = _float(value, name)
        try:
            values.append(Decimal(str(value)))
        except InvalidOperation as exc:
            raise ValueError(f"{name} must be a finite real number") from exc
    start, stop, step = values
    if start < -10 or stop > 30 or stop < -10 or start > 30:
        raise ValueError("Eb/N0 scan endpoints must be within -10..30 dB")
    if stop <= start:
        raise ValueError("stop_db must be greater than start_db")
    if step <= 0:
        raise ValueError("step_db must be greater than zero")
    intervals = (stop - start) / step
    if intervals != intervals.to_integral_value():
        raise ValueError("scan range must be evenly divisible by step_db")
    count = int(intervals) + 1
    if count > MAX_SWEEP_POINTS:
        raise ValueError(f"scan may contain at most {MAX_SWEEP_POINTS} Eb/N0 points")
    return tuple(float(start + step * index) for index in range(count))


def _received(encoding_bits: tuple[int, ...], eb_n0_db: float, seed: int) -> tuple[float, ...]:
    quantities = snr_quantities(eb_n0_db)
    rng = np.random.default_rng(np.random.SeedSequence([seed, _NOISE_TAG]))
    symbols = np.asarray([2 * bit - 1 for bit in encoding_bits], dtype=float) * quantities["coded_amplitude"]
    noise = rng.normal(0.0, quantities["noise_std"], size=len(encoding_bits))
    return tuple(float(value) for value in symbols + noise)


def _measure(reference: tuple[int, ...], decisions: tuple[int, ...]) -> dict[str, int | float]:
    return ber(reference, decisions)


def run_compare(
    n_information_bits: int = 256,
    eb_n0_db: float = 4.0,
    seed: int = 2026,
    *,
    include_details: bool = False,
) -> dict[str, object]:
    n = _information_length(n_information_bits)
    eb_n0 = _float(eb_n0_db, "eb_n0_db")
    if not -10 <= eb_n0 <= 30:
        raise ValueError("eb_n0_db must be within -10..30 dB")
    root_seed = _seed(seed)
    if include_details and n > MAX_DETAIL_INFORMATION_BITS:
        raise ValueError(f"include_details is limited to {MAX_DETAIL_INFORMATION_BITS} information bits")
    information = _payload(root_seed, n)
    encoding = encode_frame(information)
    received = _received(encoding.encoded_bits, eb_n0, _point_seed(root_seed, 0))
    paired = paired_decode(information, received)
    quantities = snr_quantities(eb_n0)
    hard_stats = _measure(information, paired.hard_information_bits)
    soft_stats = _measure(information, paired.soft_information_bits)
    hard_digest = _digest(paired.received_symbols)
    comparison = (
        "本次样本中软判决信息误码更少。"
        if paired.soft_errors < paired.hard_errors
        else "本次样本中硬判决信息误码更少。"
        if paired.hard_errors < paired.soft_errors
        else "本次样本中两种判决的信息误码数相同。"
    )
    response: dict[str, object] = {
        "parameters": {
            "n_information_bits": n,
            "eb_n0_db": eb_n0,
            "seed": root_seed,
            "include_details": include_details,
        },
        "code": {
            "constraint_length": CONSTRAINT_LENGTH,
            "generators_octal": [7, 5],
            "output_order": ["g0", "g1"],
            "rate": CODE_RATE,
            "tail_bits": list(TAIL_BITS),
            "decoder": "terminated_hard_and_soft_viterbi",
        },
        "energy": {
            "eb_info": quantities["eb_info"],
            "coded_symbol_energy": quantities["coded_symbol_energy"],
            "coded_amplitude": quantities["coded_amplitude"],
            "noise_variance": quantities["noise_variance"],
            "noise_std": quantities["noise_std"],
        },
        "lengths": {
            "information_bits": n,
            "tail_bits": len(TAIL_BITS),
            "encoded_bits": len(encoding.encoded_bits),
            "decoded_information_bits": len(paired.soft_information_bits),
        },
        "fairness": {
            "same_received_samples": True,
            "received_samples_sha256": hard_digest,
            "hard_input_sha256": hard_digest,
            "soft_input_sha256": hard_digest,
            "noise_draws": 1,
        },
        "results": {
            "hard_decision": {**hard_stats, "path_metric": paired.hard_path_metric, "tail_counted": False},
            "soft_decision": {**soft_stats, "path_metric": paired.soft_path_metric, "metric_scale": paired.soft_metric_scale, "tail_counted": False},
            "outputs_equal": paired.hard_information_bits == paired.soft_information_bits,
            "decoded_tail_bits": [0, 0],
        },
        "teaching": {
            "fairness": "硬判决和软判决消费同一组接收样本；差异来自是否保留样本幅度信息，而不是两次不同的噪声抽样。",
            "observation": comparison,
            "limitation": "有限长度的实测 BER 具有随机性；零误码只表示本次样本未观察到错误，不代表真实 BER 恒为零。",
        },
    }
    if include_details:
        response["details"] = {
            "information_bits": list(information),
            "encoded_bits": list(encoding.encoded_bits),
            "received_samples": list(received),
            "hard_decision_bits": list(paired.hard_decision_bits),
            "hard_information_bits": list(paired.hard_information_bits),
            "soft_information_bits": list(paired.soft_information_bits),
        }
    return response


def run_sweep(
    start_db: float = 0.0,
    stop_db: float = 10.0,
    step_db: float = 2.0,
    n_information_bits: int = 2048,
    seed: int = 2026,
) -> dict[str, object]:
    points = scan_points(start_db, stop_db, step_db)
    n = _information_length(n_information_bits, maximum=MAX_SWEEP_INFORMATION_BITS)
    total = len(points) * n
    if total > MAX_SWEEP_TOTAL_INFORMATION_BITS:
        raise ValueError(f"sweep may process at most {MAX_SWEEP_TOTAL_INFORMATION_BITS} information bits total")
    root_seed = _seed(seed)
    information = _payload(root_seed, n)
    encoding = encode_frame(information)
    results: list[dict[str, object]] = []
    for index, eb_n0_db in enumerate(points):
        point_seed = _point_seed(root_seed, index)
        received = _received(encoding.encoded_bits, eb_n0_db, point_seed)
        paired = paired_decode(information, received)
        quantities = snr_quantities(eb_n0_db)
        received_digest = _digest(received)
        results.append({
            "eb_n0_db": eb_n0_db,
            "seed": point_seed,
            "noise_variance": quantities["noise_variance"],
            "received_samples_sha256": received_digest,
            "hard_input_sha256": received_digest,
            "soft_input_sha256": received_digest,
            "hard_decision": {**_measure(information, paired.hard_information_bits), "tail_counted": False},
            "soft_decision": {**_measure(information, paired.soft_information_bits), "tail_counted": False},
            "outputs_equal": paired.hard_information_bits == paired.soft_information_bits,
        })
    return {
        "parameters": {
            "start_db": points[0], "stop_db": points[-1], "step_db": float(Decimal(str(step_db))),
            "n_information_bits": n, "seed": root_seed, "point_count": len(points),
            "total_information_bits": total,
        },
        "code": {"constraint_length": CONSTRAINT_LENGTH, "generators_octal": [7, 5], "rate": CODE_RATE, "tail_bits": list(TAIL_BITS)},
        "fairness": {"same_payload_across_points": True, "same_received_samples_per_point": True, "noise_draws_per_point": 1},
        "sampling": {"zero_error_note": "BER=0 表示有限样本中未观察到错误，不证明真实 BER 为零。"},
        "points": results,
    }


__all__ = [
    "MAX_COMPARE_INFORMATION_BITS", "MAX_DETAIL_INFORMATION_BITS", "run_compare", "run_sweep", "scan_points",
]
