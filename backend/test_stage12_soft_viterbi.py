import math
import pytest

from convolutional_coding import encode, hard_decision
from convolutional_coding import transition
from stage12_soft_viterbi import paired_decode, soft_viterbi_decode
from tests.oracles import stage12_soft_viterbi_oracle as oracle


@pytest.mark.parametrize("payload", [(1, 0), (0,), (1, 1, 1, 1), (0, 1, 0, 1, 0)])
def test_noiseless_frames_recover_payload_and_two_zero_tail_bits(payload):
    coded = encode(payload)
    received = oracle.bpsk_symbols(coded)
    result = soft_viterbi_decode(received, len(payload))
    assert result.information_bits == payload
    assert result.decoder_input_bits == payload + (0, 0)
    assert result.final_state == 0
    assert result.path_metric == 0.0
    assert result.metric_scale == pytest.approx(math.sqrt(0.5))


def test_soft_viterbi_matches_exhaustive_oracle_for_short_noisy_frames():
    for n in range(1, 7):
        for value in range(1 << n):
            payload = tuple((value >> shift) & 1 for shift in range(n - 1, -1, -1))
            coded = encode(payload)
            received = tuple(
                sample + (((index * 7 + value * 3) % 11) - 5) * 0.073
                for index, sample in enumerate(oracle.bpsk_symbols(coded))
            )
            expected = {path.information_bits for path in oracle.optimal_paths(received, n)}
            actual = soft_viterbi_decode(received, n)
            assert actual.information_bits in expected
            assert actual.decoder_input_bits[-2:] == (0, 0)


def test_fixed_zero_sample_tie_is_deterministic_and_globally_optimal():
    received = (0.0,) * 6
    expected = {path.information_bits for path in oracle.optimal_paths(received, 1)}
    first = soft_viterbi_decode(received, 1)
    assert first.information_bits in expected
    assert all(soft_viterbi_decode(received, 1) == first for _ in range(5))
    assert first.decoder_input_bits[-2:] == (0, 0)
    active = {0}
    for row in first.predecessor_states:
        for target, selected in enumerate(row):
            candidates = [
                predecessor
                for predecessor in active
                for bit in (0, 1)
                if transition(predecessor, bit)[0] == target
            ]
            assert selected == (min(candidates) if candidates else -1)
        active = {target for target, predecessor in enumerate(row) if predecessor >= 0}


def test_soft_metric_retains_amplitude_information_lost_by_hard_decision():
    received = (10.0, 10.0, -0.1, 0.1, -0.1, -0.1)
    assert hard_decision(received) == (1, 1, 0, 1, 0, 0)
    assert soft_viterbi_decode(received, 1).information_bits == (1,)


def test_paired_decode_consumes_the_same_received_tuple_and_counts_information_only():
    information = (1, 0, 1)
    received = tuple(oracle.bpsk_symbols(encode(information)))
    result = paired_decode(information, received)
    assert result.received_symbols == received
    assert result.hard_decision_bits == hard_decision(received)
    assert result.compared == len(information)
    assert result.hard_errors == sum(a != b for a, b in zip(information, result.hard_information_bits))
    assert result.soft_errors == sum(a != b for a, b in zip(information, result.soft_information_bits))
    assert result.soft_information_bits == information


def test_extreme_finite_inputs_and_long_frames_keep_finite_relative_metrics():
    result = soft_viterbi_decode((1e308, -1e308, 1e308, -1e308, 1e308, -1e308), 1)
    assert math.isfinite(result.path_metric)
    assert result.information_bits in {(0,), (1,)}
    payload = tuple((index * 13 + index // 3) % 2 for index in range(8192))
    received = oracle.bpsk_symbols(encode(payload))
    long_result = soft_viterbi_decode(received, len(payload))
    assert long_result.information_bits == payload
    assert math.isfinite(long_result.path_metric)


@pytest.mark.parametrize("received", [(), (math.nan,) * 6, (math.inf,) * 6, (True,) * 6, ("0",) * 6])
def test_invalid_samples_are_rejected(received):
    with pytest.raises(ValueError):
        soft_viterbi_decode(received, 1)


@pytest.mark.parametrize("length", [0, -1, True, 1.5])
def test_invalid_information_lengths_are_rejected(length):
    with pytest.raises(ValueError):
        soft_viterbi_decode((0.0,) * 6, length)


def test_invalid_amplitude_and_sample_count_are_rejected():
    for amplitude in (0, -1, math.inf, math.nan, True):
        with pytest.raises(ValueError):
            soft_viterbi_decode((0.0,) * 6, 1, amplitude=amplitude)
    with pytest.raises(ValueError):
        soft_viterbi_decode((0.0,) * 4, 1)
