"""Stage12 soft-input Viterbi decoding and paired hard/soft comparison."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from convolutional_coding import (
    TAIL_BITS,
    ber,
    decode_frame,
    hard_decision,
    transition,
)


DEFAULT_AMPLITUDE = math.sqrt(0.5)


@dataclass(frozen=True)
class SoftDecodeResult:
    information_bits: tuple[int, ...]
    decoder_input_bits: tuple[int, ...]
    final_state: int
    path_metric: float
    metric_scale: float
    predecessor_states: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class PairedDecodeResult:
    received_symbols: tuple[float, ...]
    hard_decision_bits: tuple[int, ...]
    hard_information_bits: tuple[int, ...]
    soft_information_bits: tuple[int, ...]
    hard_path_metric: int
    soft_path_metric: float
    soft_metric_scale: float
    hard_errors: int
    soft_errors: int
    compared: int


def _received_symbols(values: Iterable[float], information_length: int) -> tuple[float, ...]:
    if isinstance(information_length, bool) or not isinstance(information_length, (int, np.integer)) or int(information_length) < 1:
        raise ValueError("information_length must be a positive integer")
    expected = 2 * (int(information_length) + len(TAIL_BITS))
    if isinstance(values, (str, bytes)):
        raise ValueError("received_symbols must be a one-dimensional iterable of finite real numbers")
    try:
        received = tuple(values)
    except TypeError as exc:
        raise ValueError("received_symbols must be iterable") from exc
    if len(received) != expected:
        raise ValueError(f"received_symbols must contain exactly {expected} samples")
    normalized: list[float] = []
    for value in received:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError("received_symbols must contain finite real numbers")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("received_symbols must contain finite real numbers")
        normalized.append(numeric)
    return tuple(normalized)


def soft_viterbi_decode(
    received_symbols: Iterable[float],
    information_length: int,
    *,
    amplitude: float = DEFAULT_AMPLITUDE,
) -> SoftDecodeResult:
    """Decode a terminated frame with AWGN maximum-likelihood Euclidean metric.

    The returned metric is a relative squared distance: the minimum survivor
    metric is subtracted at every trellis step, and all samples and symbols
    share ``metric_scale`` to keep finite extreme inputs representable.
    """
    received = _received_symbols(received_symbols, information_length)
    if isinstance(amplitude, bool) or not isinstance(amplitude, (int, float, np.integer, np.floating)):
        raise ValueError("amplitude must be a finite positive real number")
    amplitude = float(amplitude)
    if not math.isfinite(amplitude) or amplitude <= 0:
        raise ValueError("amplitude must be a finite positive real number")

    scale = max(amplitude, *(abs(value) for value in received))
    scaled_amplitude = amplitude / scale
    scaled_received = tuple(value / scale for value in received)
    n = int(information_length)
    metrics = [math.inf] * 4
    metrics[0] = 0.0
    predecessors: list[list[int]] = []
    decisions: list[list[int]] = []

    for time in range(n + len(TAIL_BITS)):
        pair = scaled_received[2 * time : 2 * time + 2]
        next_metrics = [math.inf] * 4
        next_predecessors = [-1] * 4
        next_decisions = [-1] * 4
        for predecessor in range(4):
            if math.isinf(metrics[predecessor]):
                continue
            for bit in (0, 1):
                target, output = transition(predecessor, bit)
                branch_metric = 0.0
                for sample, coded_bit in zip(pair, output):
                    transmitted = scaled_amplitude if coded_bit else -scaled_amplitude
                    branch_metric += (sample - transmitted) ** 2
                candidate = metrics[predecessor] + branch_metric
                current_predecessor = next_predecessors[target]
                if candidate < next_metrics[target] or (
                    candidate == next_metrics[target]
                    and (current_predecessor < 0 or predecessor < current_predecessor)
                ):
                    next_metrics[target] = candidate
                    next_predecessors[target] = predecessor
                    next_decisions[target] = bit
        finite_metrics = [metric for metric in next_metrics if math.isfinite(metric)]
        if not finite_metrics:
            raise ValueError("soft path metric is outside the representable range")
        offset = min(finite_metrics)
        next_metrics = [metric - offset if math.isfinite(metric) else math.inf for metric in next_metrics]
        predecessors.append(next_predecessors)
        decisions.append(next_decisions)
        metrics = next_metrics

    state = 0
    decoded_reversed: list[int] = []
    for time in range(len(decisions) - 1, -1, -1):
        predecessor = predecessors[time][state]
        bit = decisions[time][state]
        if predecessor < 0 or bit < 0:
            raise ValueError("failed to reconstruct a terminated trellis path")
        decoded_reversed.append(bit)
        state = predecessor
    if state != 0:
        raise AssertionError("soft Viterbi traceback did not return to the known initial state")
    decoder_inputs = tuple(reversed(decoded_reversed))
    if decoder_inputs[-2:] != TAIL_BITS:
        raise AssertionError("terminated soft path must end with two zero tail decisions")
    return SoftDecodeResult(
        information_bits=decoder_inputs[:-2],
        decoder_input_bits=decoder_inputs,
        final_state=0,
        path_metric=metrics[0],
        metric_scale=scale,
        predecessor_states=tuple(tuple(row) for row in predecessors),
    )


def paired_decode(
    information_bits: Iterable[int],
    received_symbols: Iterable[float],
    *,
    amplitude: float = DEFAULT_AMPLITUDE,
) -> PairedDecodeResult:
    """Run hard and soft decoders on the same immutable received tuple."""
    from convolutional_coding import _bits

    information = _bits(information_bits, name="information_bits")
    received = _received_symbols(received_symbols, len(information))
    hard_bits = hard_decision(received)
    hard_result = decode_frame(hard_bits, len(information))
    soft_result = soft_viterbi_decode(received, len(information), amplitude=amplitude)
    hard_stats = ber(information, hard_result.information_bits)
    soft_stats = ber(information, soft_result.information_bits)
    return PairedDecodeResult(
        received_symbols=received,
        hard_decision_bits=hard_bits,
        hard_information_bits=hard_result.information_bits,
        soft_information_bits=soft_result.information_bits,
        hard_path_metric=hard_result.path_metric,
        soft_path_metric=soft_result.path_metric,
        soft_metric_scale=soft_result.metric_scale,
        hard_errors=int(hard_stats["errors"]),
        soft_errors=int(soft_stats["errors"]),
        compared=len(information),
    )


__all__ = ["DEFAULT_AMPLITUDE", "PairedDecodeResult", "SoftDecodeResult", "paired_decode", "soft_viterbi_decode"]
