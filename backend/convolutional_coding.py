"""Stage10 fixed convolutional coding and reproducible AWGN experiments.

The module intentionally implements only the Phase 1 contract: a terminated
K=3, rate-1/2, (7, 5) convolutional code with hard-decision Viterbi decoding.
It is independent of the existing Stage01--09 simulators.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable, Sequence

import numpy as np


CONSTRAINT_LENGTH = 3
MEMORY = 2
GENERATORS_OCTAL = (7, 5)
CODE_RATE = 0.5
TAIL_BITS = (0, 0)
EB_INFO = 1.0


def _bits(values: Iterable[int], *, name: str = "bits") -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a one-dimensional iterable of integer 0/1 values")
    try:
        result = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be an iterable") from exc
    if not result:
        raise ValueError(f"{name} must not be empty")
    for bit in result:
        if isinstance(bit, bool) or not isinstance(bit, (int, np.integer)) or int(bit) not in (0, 1):
            raise ValueError(f"each {name} value must be an integer 0 or 1; bool is not accepted")
    return tuple(int(bit) for bit in result)


def _information_length(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or int(value) < 1:
        raise ValueError("information_length must be a positive integer")
    return int(value)


def transition(state: int, input_bit: int) -> tuple[int, tuple[int, int]]:
    """Return ``(next_state, (g0, g1))`` for the fixed four-state trellis."""
    if isinstance(state, bool) or not isinstance(state, (int, np.integer)) or int(state) not in range(4):
        raise ValueError("state must be an integer in 0..3")
    if isinstance(input_bit, bool) or not isinstance(input_bit, (int, np.integer)) or int(input_bit) not in (0, 1):
        raise ValueError("input_bit must be an integer 0 or 1")
    state = int(state)
    bit = int(input_bit)
    m1, m2 = divmod(state, 2)
    return 2 * bit + m1, (bit ^ m1 ^ m2, bit ^ m2)


def encode(information_bits: Iterable[int]) -> tuple[int, ...]:
    """Encode payload bits and append exactly two zero termination inputs."""
    information = _bits(information_bits, name="information_bits")
    state = 0
    coded: list[int] = []
    for bit in information + TAIL_BITS:
        state, pair = transition(state, bit)
        coded.extend(pair)
    if state != 0:  # defensive assertion of the fixed two-bit termination rule
        raise AssertionError("two zero tail bits must return the encoder to state zero")
    return tuple(coded)


@dataclass(frozen=True)
class EncodingResult:
    information_bits: tuple[int, ...]
    encoder_input_bits: tuple[int, ...]
    encoded_bits: tuple[int, ...]
    tail_bits: int = 2
    constraint_length: int = CONSTRAINT_LENGTH
    code_rate: float = CODE_RATE

    @property
    def information_length(self) -> int:
        return len(self.information_bits)

    @property
    def encoded_length(self) -> int:
        return len(self.encoded_bits)


def encode_frame(information_bits: Iterable[int]) -> EncodingResult:
    information = _bits(information_bits, name="information_bits")
    return EncodingResult(information, information + TAIL_BITS, encode(information))


@dataclass(frozen=True)
class DecodeResult:
    information_bits: tuple[int, ...]
    decoder_input_bits: tuple[int, ...]
    final_state: int
    path_metric: int
    predecessor_states: tuple[tuple[int, ...], ...]


def _received_bits(received_bits: Iterable[int]) -> tuple[int, ...]:
    return _bits(received_bits, name="received_bits")


def decode_frame(received_bits: Iterable[int], information_length: int) -> DecodeResult:
    """Hard-decision terminated Viterbi decode with deterministic tie-breaking."""
    n = _information_length(information_length)
    received = _received_bits(received_bits)
    expected_length = 2 * (n + len(TAIL_BITS))
    if len(received) != expected_length:
        raise ValueError(f"received_bits must contain exactly {expected_length} bits for information_length={n}")

    # For every time and target state retain the best predecessor.  Equal
    # metrics select the numerically smaller predecessor state (Phase 1 rule).
    metrics = [math.inf] * 4
    metrics[0] = 0
    predecessors: list[list[int]] = []
    decisions: list[list[int]] = []
    for time in range(n + len(TAIL_BITS)):
        pair = received[2 * time : 2 * time + 2]
        next_metrics = [math.inf] * 4
        next_predecessors = [-1] * 4
        next_decisions = [-1] * 4
        for predecessor in range(4):
            if math.isinf(metrics[predecessor]):
                continue
            for bit in (0, 1):
                target, output = transition(predecessor, bit)
                branch_metric = int(output[0] != pair[0]) + int(output[1] != pair[1])
                candidate = metrics[predecessor] + branch_metric
                current_predecessor = next_predecessors[target]
                if candidate < next_metrics[target] or (
                    candidate == next_metrics[target]
                    and (current_predecessor < 0 or predecessor < current_predecessor)
                ):
                    next_metrics[target] = candidate
                    next_predecessors[target] = predecessor
                    next_decisions[target] = bit
        predecessors.append(next_predecessors)
        decisions.append(next_decisions)
        metrics = next_metrics

    if math.isinf(metrics[0]):
        raise ValueError("received_bits has no path terminating in state zero")
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
        raise AssertionError("Viterbi traceback did not return to the known initial state")
    decoder_inputs = tuple(reversed(decoded_reversed))
    if decoder_inputs[-2:] != TAIL_BITS:
        raise AssertionError("terminated Viterbi path must end with two zero tail decisions")
    return DecodeResult(decoder_inputs[:-2], decoder_inputs, 0, int(metrics[0]), tuple(tuple(row) for row in predecessors))


def viterbi_decode(received_bits: Iterable[int], information_length: int) -> tuple[int, ...]:
    """Return only the information payload from a terminated hard Viterbi decode."""
    return decode_frame(received_bits, information_length).information_bits


def hard_decision(received_symbols: Iterable[float]) -> tuple[int, ...]:
    """Map real BPSK samples using the Stage01 convention ``sample > 0``."""
    try:
        values = tuple(received_symbols)
    except TypeError as exc:
        raise ValueError("received_symbols must be an iterable") from exc
    if not values:
        raise ValueError("received_symbols must not be empty")
    result: list[int] = []
    for value in values:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError("received_symbols must contain finite real numbers")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("received_symbols must contain finite real numbers")
        result.append(int(numeric > 0.0))
    return tuple(result)


def snr_quantities(eb_n0_db: float, *, eb_info: float = EB_INFO) -> dict[str, float]:
    """Return the fixed information-energy AWGN quantities for one experiment."""
    if isinstance(eb_n0_db, bool) or not isinstance(eb_n0_db, (int, float, np.integer, np.floating)):
        raise ValueError("eb_n0_db must be a finite real number")
    if isinstance(eb_info, bool) or not isinstance(eb_info, (int, float, np.integer, np.floating)):
        raise ValueError("eb_info must be a finite positive real number")
    eb_n0_db = float(eb_n0_db)
    eb_info = float(eb_info)
    if not math.isfinite(eb_n0_db) or not math.isfinite(eb_info) or eb_info <= 0:
        raise ValueError("eb_n0_db must be finite and eb_info must be positive")
    try:
        gamma_b = 10.0 ** (eb_n0_db / 10.0)
        n0 = eb_info / gamma_b
        noise_variance = n0 / 2.0
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("Eb/N0 is outside the representable range") from exc
    if not all(math.isfinite(value) for value in (gamma_b, n0, noise_variance)) or noise_variance <= 0:
        raise ValueError("Eb/N0 is outside the representable range")
    return {
        "gamma_b": gamma_b,
        "n0": n0,
        "noise_variance": noise_variance,
        "noise_std": math.sqrt(noise_variance),
        "eb_info": eb_info,
        "code_rate": CODE_RATE,
        "uncoded_symbol_energy": eb_info,
        "coded_symbol_energy": CODE_RATE * eb_info,
        "uncoded_amplitude": math.sqrt(eb_info),
        "coded_amplitude": math.sqrt(CODE_RATE * eb_info),
    }


def ber(reference: Iterable[int], decisions: Iterable[int]) -> dict[str, int | float]:
    expected = _bits(reference, name="reference")
    actual = _bits(decisions, name="decisions")
    if len(expected) != len(actual):
        raise ValueError("reference and decisions must have equal lengths")
    errors = sum(left != right for left, right in zip(expected, actual))
    return {"errors": errors, "compared": len(expected), "ber": errors / len(expected)}


@dataclass(frozen=True)
class ExperimentResult:
    information_bits: tuple[int, ...]
    encoded_bits: tuple[int, ...]
    uncoded_received: tuple[float, ...]
    coded_received: tuple[float, ...]
    uncoded_hard_decisions: tuple[int, ...]
    coded_hard_decisions: tuple[int, ...]
    decoded_information_bits: tuple[int, ...]
    information_bit_count: int
    encoded_bit_count: int
    tail_bit_count: int
    encoded_symbol_count: int
    eb_n0_db: float
    noise_variance: float
    noise_std: float
    random_seed: int
    code_rate: float
    eb_info: float
    uncoded_errors: int
    uncoded_ber: float
    coded_channel_errors: int
    coded_channel_ber: float
    decoded_information_errors: int
    decoded_information_ber: float
    decoded_information_length: int
    decoded_tail_bits: tuple[int, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _seed(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= int(value) <= 2**32 - 1:
        raise ValueError("seed must be an integer in [0, 2**32-1]")
    return int(value)


def run_experiment(
    n_information_bits: int,
    eb_n0_db: float,
    seed: int,
    *,
    information_bits: Iterable[int] | None = None,
) -> ExperimentResult:
    """Run both fair BPSK links once with deterministic independent RNG streams."""
    n = _information_length(n_information_bits)
    seed_value = _seed(seed)
    quantities = snr_quantities(eb_n0_db)
    streams = np.random.SeedSequence(seed_value).spawn(3)
    if information_bits is None:
        info = tuple(int(bit) for bit in np.random.default_rng(streams[0]).integers(0, 2, size=n))
    else:
        info = _bits(information_bits, name="information_bits")
        if len(info) != n:
            raise ValueError("information_bits length must equal n_information_bits")
    encoding = encode_frame(info)
    uncoded_rng = np.random.default_rng(streams[1])
    coded_rng = np.random.default_rng(streams[2])
    uncoded_noise = uncoded_rng.normal(0.0, quantities["noise_std"], size=n)
    coded_noise = coded_rng.normal(0.0, quantities["noise_std"], size=len(encoding.encoded_bits))
    uncoded_symbols = np.asarray([2 * bit - 1 for bit in info], dtype=float) * quantities["uncoded_amplitude"]
    coded_symbols = np.asarray([2 * bit - 1 for bit in encoding.encoded_bits], dtype=float) * quantities["coded_amplitude"]
    uncoded_received = uncoded_symbols + uncoded_noise
    coded_received = coded_symbols + coded_noise
    uncoded_decisions = hard_decision(uncoded_received)
    coded_decisions = hard_decision(coded_received)
    decoded = decode_frame(coded_decisions, n)
    uncoded_stats = ber(info, uncoded_decisions)
    coded_stats = ber(encoding.encoded_bits, coded_decisions)
    decoded_stats = ber(info, decoded.information_bits)
    return ExperimentResult(
        information_bits=info,
        encoded_bits=encoding.encoded_bits,
        uncoded_received=tuple(float(value) for value in uncoded_received),
        coded_received=tuple(float(value) for value in coded_received),
        uncoded_hard_decisions=uncoded_decisions,
        coded_hard_decisions=coded_decisions,
        decoded_information_bits=decoded.information_bits,
        information_bit_count=n,
        encoded_bit_count=len(encoding.encoded_bits),
        tail_bit_count=2,
        encoded_symbol_count=len(encoding.encoded_bits),
        eb_n0_db=float(eb_n0_db),
        noise_variance=quantities["noise_variance"],
        noise_std=quantities["noise_std"],
        random_seed=seed_value,
        code_rate=CODE_RATE,
        eb_info=quantities["eb_info"],
        uncoded_errors=int(uncoded_stats["errors"]),
        uncoded_ber=float(uncoded_stats["ber"]),
        coded_channel_errors=int(coded_stats["errors"]),
        coded_channel_ber=float(coded_stats["ber"]),
        decoded_information_errors=int(decoded_stats["errors"]),
        decoded_information_ber=float(decoded_stats["ber"]),
        decoded_information_length=len(decoded.information_bits),
        decoded_tail_bits=(decoded.decoder_input_bits[-2], decoded.decoder_input_bits[-1]),
    )


simulate_experiment = run_experiment


__all__ = [
    "CODE_RATE", "CONSTRAINT_LENGTH", "EB_INFO", "EncodingResult", "ExperimentResult",
    "GENERATORS_OCTAL", "TAIL_BITS", "ber", "decode_frame", "encode", "encode_frame",
    "hard_decision", "run_experiment", "simulate_experiment", "snr_quantities", "transition",
    "viterbi_decode",
]
