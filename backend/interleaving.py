"""Production block interleaver and deterministic burst-error channel.

Blocks are written row-major and read column-major, matching the Stage11
Phase 1 contract. Public results are immutable tuples so padding and channel
coordinates remain explicit and callers' buffers are never modified.
"""
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable

import numpy as np


MAX_DIMENSION = 4096
MAX_BLOCK_BITS = 1_048_576
MAX_SEQUENCE_BITS = 4_194_304


def _bits(values: Iterable[int], *, name: str = "bits") -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a one-dimensional iterable of integer 0/1 values")
    if isinstance(values, np.ndarray) and values.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    try:
        result = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be iterable") from exc
    if len(result) > MAX_SEQUENCE_BITS:
        raise ValueError(f"{name} exceeds the {MAX_SEQUENCE_BITS}-bit limit")
    if any(isinstance(bit, (bool, np.bool_)) or not isinstance(bit, (int, np.integer)) or int(bit) not in (0, 1) for bit in result):
        raise ValueError(f"{name} must contain integer 0/1 values; bool and non-integer dtypes are not accepted")
    return tuple(int(bit) for bit in result)


def _dimensions(rows: int, columns: int) -> tuple[int, int]:
    if type(rows) is not int or type(columns) is not int or rows < 1 or columns < 1:
        raise ValueError("rows and columns must be positive integers")
    if rows > MAX_DIMENSION or columns > MAX_DIMENSION or rows * columns > MAX_BLOCK_BITS:
        raise ValueError(f"block dimensions exceed limits ({MAX_DIMENSION} per axis, {MAX_BLOCK_BITS} bits total)")
    return rows, columns


@dataclass(frozen=True)
class InterleavedBits:
    bits: tuple[int, ...]
    valid_length: int
    padded_length: int
    pad_count: int
    output_sources: tuple[int | None, ...]


@dataclass(frozen=True)
class BurstResult:
    bits: tuple[int, ...]
    start: int
    length: int
    flipped_positions: tuple[int, ...]
    flipped_count: int
    valid_length: int


def interleave_bits(values: Iterable[int], rows: int, columns: int) -> InterleavedBits:
    """Pad complete rectangles with zeroes, then emit each block column-first."""
    data = _bits(values)
    rows, columns = _dimensions(rows, columns)
    block = rows * columns
    padded_length = ((len(data) + block - 1) // block) * block
    if padded_length > MAX_SEQUENCE_BITS:
        raise ValueError(f"padded sequence exceeds the {MAX_SEQUENCE_BITS}-bit limit")
    padded = data + (0,) * (padded_length - len(data))
    output: list[int] = []
    sources: list[int | None] = []
    for base in range(0, padded_length, block):
        for column in range(columns):
            for row in range(rows):
                source = base + row * columns + column
                output.append(padded[source])
                sources.append(source if source < len(data) else None)
    return InterleavedBits(tuple(output), len(data), padded_length, padded_length - len(data), tuple(sources))


def deinterleave_bits(values: Iterable[int], valid_length: int, rows: int, columns: int) -> tuple[int, ...]:
    """Invert column-first block transmission and discard only known padding."""
    received = _bits(values, name="interleaved bits")
    rows, columns = _dimensions(rows, columns)
    if type(valid_length) is not int or valid_length < 0 or valid_length > MAX_SEQUENCE_BITS:
        raise ValueError(f"valid_length must be an integer in [0, {MAX_SEQUENCE_BITS}]")
    block = rows * columns
    expected = ((valid_length + block - 1) // block) * block
    if len(received) != expected:
        raise ValueError(f"interleaved sequence must contain exactly {expected} bits for valid_length")
    restored: list[int] = []
    for base in range(0, expected, block):
        matrix = [0] * block
        cursor = base
        for column in range(columns):
            for row in range(rows):
                matrix[row * columns + column] = received[cursor]
                cursor += 1
        restored.extend(matrix)
    return tuple(restored[:valid_length])


def apply_burst_errors(
    values: Iterable[int], length: int, *, start: int | None = 0, seed: int | None = None,
) -> BurstResult:
    """Flip one contiguous burst in transmission coordinates.

    Supply an explicit ``start`` (the default is zero), or pass ``start=None``
    with a nonnegative ``seed`` to draw a reproducible legal start from a local
    RNG. The burst must fit entirely within the supplied single-frame sequence.
    """
    bits = _bits(values, name="transmitted bits")
    if type(length) is not int or length < 0 or length > len(bits):
        raise ValueError("length must be an integer between zero and the sequence length")
    if start is None:
        if seed is None or type(seed) is not int or seed < 0:
            raise ValueError("a nonnegative integer seed is required when start is None")
        actual_start = random.Random(seed).randrange(len(bits) - length + 1)
    else:
        if type(start) is not int or seed is not None or start < 0:
            raise ValueError("start must be a nonnegative integer; seed is only valid when start is None")
        actual_start = start
    if actual_start > len(bits) or actual_start + length > len(bits):
        raise ValueError("burst must lie wholly inside the single-frame sequence")
    positions = tuple(range(actual_start, actual_start + length))
    changed = list(bits)
    for position in positions:
        changed[position] ^= 1
    return BurstResult(tuple(changed), actual_start, length, positions, len(positions), len(bits))
