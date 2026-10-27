"""Independent exhaustive soft-decision oracle for Stage12 Phase 1.

The oracle enumerates terminated payload paths and scores their BPSK waveforms
with squared Euclidean distance. It deliberately does not import the
production convolutional module or reproduce its dynamic-programming decoder.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


CONSTRAINT_LENGTH = 3
CODE_RATE = 0.5
TAIL_BITS = (0, 0)
EB_INFO = 1.0
DEFAULT_AMPLITUDE = math.sqrt(CODE_RATE * EB_INFO)


def _payload(values: Iterable[int]) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("information_bits must be an iterable of integer 0/1 values")
    try:
        result = tuple(values)
    except TypeError as exc:
        raise ValueError("information_bits must be iterable") from exc
    if not result:
        raise ValueError("information_bits must not be empty")
    if any(isinstance(bit, bool) or not isinstance(bit, int) or bit not in (0, 1) for bit in result):
        raise ValueError("information_bits must contain only integer 0/1 values")
    return result


def _information_length(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("information_length must be a positive integer")
    return value


def transition(state: int, input_bit: int) -> tuple[int, tuple[int, int]]:
    """Independent scalar (7,5) transition; state is 2*m1+m2."""
    if isinstance(state, bool) or not isinstance(state, int) or state not in range(4):
        raise ValueError("state must be an integer in 0..3")
    if isinstance(input_bit, bool) or not isinstance(input_bit, int) or input_bit not in (0, 1):
        raise ValueError("input_bit must be integer 0 or 1")
    m1, m2 = divmod(state, 2)
    return 2 * input_bit + m1, (input_bit ^ m1 ^ m2, input_bit ^ m2)


def encode_payload(information_bits: Iterable[int]) -> tuple[int, ...]:
    """Encode a payload with exactly two zero termination inputs."""
    payload = _payload(information_bits)
    state = 0
    encoded: list[int] = []
    for bit in payload + TAIL_BITS:
        state, pair = transition(state, bit)
        encoded.extend(pair)
    if state != 0:
        raise AssertionError("two zero tail inputs must terminate at state zero")
    return tuple(encoded)


def bpsk_symbols(bits: Iterable[int], amplitude: float = DEFAULT_AMPLITUDE) -> tuple[float, ...]:
    """Map 0 to -amplitude and 1 to +amplitude."""
    if isinstance(amplitude, bool) or not isinstance(amplitude, (int, float)):
        raise ValueError("amplitude must be a finite positive real number")
    amplitude = float(amplitude)
    if not math.isfinite(amplitude) or amplitude <= 0:
        raise ValueError("amplitude must be a finite positive real number")
    try:
        values = tuple(bits)
    except TypeError as exc:
        raise ValueError("bits must be iterable") from exc
    if not values or any(isinstance(bit, bool) or not isinstance(bit, int) or bit not in (0, 1) for bit in values):
        raise ValueError("bits must contain at least one integer 0/1 value")
    return tuple(amplitude * (2 * bit - 1) for bit in values)


def _received(values: Iterable[float], expected_length: int) -> tuple[float, ...]:
    try:
        result = tuple(values)
    except TypeError as exc:
        raise ValueError("received_symbols must be iterable") from exc
    if len(result) != expected_length:
        raise ValueError(f"received_symbols must contain exactly {expected_length} samples")
    normalized: list[float] = []
    for value in result:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("received_symbols must contain finite real numbers")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("received_symbols must contain finite real numbers")
        normalized.append(numeric)
    return tuple(normalized)


@dataclass(frozen=True)
class SoftPath:
    information_bits: tuple[int, ...]
    encoder_input_bits: tuple[int, ...]
    encoded_bits: tuple[int, ...]
    distance: float


def path_distance(received_symbols: Iterable[float], encoded_bits: Iterable[int], amplitude: float = DEFAULT_AMPLITUDE) -> float:
    """Return the unnormalized AWGN squared Euclidean distance."""
    encoded = tuple(encoded_bits)
    received = _received(received_symbols, len(encoded))
    symbols = bpsk_symbols(encoded, amplitude)
    total = 0.0
    for received_value, transmitted_value in zip(received, symbols):
        try:
            term = (received_value - transmitted_value) ** 2
        except OverflowError as exc:
            raise ValueError("squared distance overflowed finite floating-point range") from exc
        total += term
        if not math.isfinite(total):
            raise ValueError("squared distance overflowed finite floating-point range")
    return total


def enumerate_paths(
    received_symbols: Iterable[float], information_length: int, amplitude: float = DEFAULT_AMPLITUDE,
) -> tuple[SoftPath, ...]:
    """Enumerate every payload path satisfying the zero-tail termination rule."""
    n = _information_length(information_length)
    received = _received(received_symbols, 2 * (n + len(TAIL_BITS)))
    paths: list[SoftPath] = []
    for value in range(1 << n):
        payload = tuple((value >> shift) & 1 for shift in range(n - 1, -1, -1))
        encoded = encode_payload(payload)
        paths.append(SoftPath(payload, payload + TAIL_BITS, encoded, path_distance(received, encoded, amplitude)))
    return tuple(paths)


def optimal_paths(
    received_symbols: Iterable[float], information_length: int, amplitude: float = DEFAULT_AMPLITUDE,
) -> tuple[SoftPath, ...]:
    """Return all globally minimum-distance terminated paths."""
    paths = enumerate_paths(received_symbols, information_length, amplitude)
    minimum = min(path.distance for path in paths)
    return tuple(path for path in paths if path.distance == minimum)


__all__ = [
    "CODE_RATE", "CONSTRAINT_LENGTH", "DEFAULT_AMPLITUDE", "EB_INFO", "SoftPath", "TAIL_BITS",
    "bpsk_symbols", "encode_payload", "enumerate_paths", "optimal_paths", "path_distance", "transition",
]
