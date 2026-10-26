"""Production acceptance tests for Stage11 Phase 2 interleaving and bursts."""
import numpy as np
import pytest

from tests.oracles import stage11_interleaving_oracle as oracle
from interleaving import apply_burst_errors, deinterleave_bits, interleave_bits
import convolutional_coding as coding


@pytest.mark.parametrize("rows,columns,data", [
    (2, 3, (0, 1, 0, 1, 1, 0)), (1, 4, (1, 0, 1)),
    (4, 1, (1, 0, 1)), (1, 1, (1,)), (2, 2, (1,)),
    (3, 2, ()),
])
def test_interleaver_matches_oracle_for_shapes_padding_and_empty(rows, columns, data):
    got = interleave_bits(data, rows, columns)
    expected = oracle.interleave(data, rows, columns)
    assert (got.bits, got.valid_length, got.padded_length, got.pad_count, got.output_sources) == (
        expected.bits, expected.valid_length, expected.padded_length, expected.pad_count, expected.output_sources
    )
    assert deinterleave_bits(got.bits, got.valid_length, rows, columns) == data


def test_multiple_blocks_and_varied_shapes_are_exact_permutations():
    for rows, columns in ((1, 2), (2, 1), (2, 3), (3, 4)):
        for length in range(0, rows * columns * 3 + 1):
            source = tuple((i * 5 + length) % 2 for i in range(length))
            output = interleave_bits(source, rows, columns)
            assert deinterleave_bits(output.bits, length, rows, columns) == source
            assert tuple(output.output_sources.count(i) for i in range(length)) == (1,) * length


@pytest.mark.parametrize("rows,columns", [(0, 1), (1, 0), (-1, 2), (True, 2), (4097, 1), (1024, 1025)])
def test_invalid_or_oversized_dimensions_rejected(rows, columns):
    with pytest.raises(ValueError):
        interleave_bits((1,), rows, columns)


@pytest.mark.parametrize("data", [(0, 2), (True,), (0.0,), ("0",), ((0, 1),), np.array([[0, 1]])])
def test_invalid_bit_values_and_array_shapes_rejected(data):
    with pytest.raises(ValueError):
        interleave_bits(data, 2, 2)


def test_numpy_integer_vector_accepted_and_input_never_mutated():
    source = np.array([1, 0, 1], dtype=np.int8)
    before = source.copy()
    result = interleave_bits(source, 2, 2)
    assert result.bits == (1, 1, 0, 0)
    assert np.array_equal(source, before)


@pytest.mark.parametrize("data,valid,rows,columns", [
    ((0, 1), 3, 2, 2), ((0, 1, 0), 2, 2, 2), ((0,), -1, 1, 1),
    ((0,), True, 1, 1),
])
def test_deinterleaver_rejects_length_and_shape_mismatches(data, valid, rows, columns):
    with pytest.raises(ValueError):
        deinterleave_bits(data, valid, rows, columns)


@pytest.mark.parametrize("start,length,expected", [
    (0, 0, ()), (0, 1, (0,)), (2, 3, (2, 3, 4)), (5, 0, ()),
])
def test_burst_boundaries_and_exact_flip_metadata(start, length, expected):
    source = (0, 1, 0, 1, 0)
    before = source
    result = apply_burst_errors(source, length, start=start)
    assert result.flipped_positions == expected
    assert result.flipped_count == length
    assert result.valid_length == len(source)
    assert tuple(i for i, (a, b) in enumerate(zip(source, result.bits)) if a != b) == expected
    assert source == before


@pytest.mark.parametrize("start,length", [(-1, 1), (6, 0), (4, 2), (0, -1), (0, 6)])
def test_burst_rejects_out_of_range_requests(start, length):
    with pytest.raises(ValueError):
        apply_burst_errors((0, 1, 0, 1, 0), length, start=start)


def test_empty_and_seeded_bursts_are_reproducible_without_global_rng():
    assert apply_burst_errors((), 0, start=0).bits == ()
    first = apply_burst_errors((0,) * 20, 5, start=None, seed=71)
    second = apply_burst_errors((0,) * 20, 5, start=None, seed=71)
    assert first == second
    assert first.start == oracle.seeded_burst_start(20, 5, 71)
    with pytest.raises(ValueError):
        apply_burst_errors((0, 1), 1, start=None)
    with pytest.raises(ValueError):
        apply_burst_errors((0, 1), 1, start=0, seed=1)


def test_interleave_burst_deinterleave_matches_independent_index_oracle():
    source = (0, 1, 0, 1, 1, 0)
    expected_interleaved = oracle.interleave(source, 2, 3)
    interleaved = interleave_bits(source, 2, 3)
    assert interleaved.bits == expected_interleaved.bits == (0, 1, 1, 1, 0, 0)
    channel = apply_burst_errors(interleaved.bits, 3, start=1)
    assert channel.flipped_positions == oracle.burst_positions(6, 1, 3)
    recovered = deinterleave_bits(channel.bits, len(source), 2, 3)
    expected = oracle.flip_at(source, oracle.mapped_burst(expected_interleaved.output_sources, channel.flipped_positions))
    assert recovered == expected


def test_errors_on_padding_do_not_enter_valid_codeword():
    source = (1, 1, 1, 0, 0, 0, 1, 0, 1, 1)
    coded = interleave_bits(source, 2, 3)
    assert coded.pad_count == 2
    pad_positions = tuple(i for i, item in enumerate(coded.output_sources) if item is None)
    assert pad_positions == (9, 11)
    # Two isolated positions can be flipped without treating intervening valid data as part of a burst.
    noisy = list(coded.bits)
    for i in pad_positions:
        noisy[i] ^= 1
    assert deinterleave_bits(noisy, len(source), 2, 3) == source


def test_stage10_fair_chain_uses_channel_coordinates_and_information_denominator():
    payload = (1, 0, 1, 1, 0)
    codeword = coding.encode(payload)
    plain_channel = apply_burst_errors(codeword, 3, start=4)
    plain_decoded = coding.viterbi_decode(plain_channel.bits, len(payload))

    interleaved = interleave_bits(codeword, 2, 3)
    channel = apply_burst_errors(interleaved.bits, 3, start=4)
    restored = deinterleave_bits(channel.bits, len(codeword), 2, 3)
    decoded = coding.viterbi_decode(restored, len(payload))

    expected_positions = oracle.mapped_burst(interleaved.output_sources, channel.flipped_positions)
    actual_positions = tuple(i for i, (a, b) in enumerate(zip(codeword, restored)) if a != b)
    assert actual_positions == expected_positions
    assert len(codeword) == 2 * (len(payload) + 2) == 14
    assert len(interleaved.bits) == 18 and interleaved.pad_count == 4
    assert channel.flipped_count == 3
    assert len(plain_decoded) == len(decoded) == len(payload)
    assert len(payload) == 5  # decoded information BER denominator; tails and pad are excluded
    frame = coding.decode_frame(restored, len(payload))
    assert frame.information_bits == decoded
    assert frame.decoder_input_bits[-2:] == (0, 0)


def test_mutation_controls_detect_contract_breaks_in_isolated_fixtures():
    source = (0, 1, 0, 1, 1, 0)
    locked = oracle.interleave(source, 2, 3)
    produced = interleave_bits(source, 2, 3)
    assert produced.bits == locked.bits
    assert tuple(reversed(produced.bits)) != locked.bits  # reversed read order
    wrong_inverse = tuple(produced.bits[i] for i in (0, 1, 3, 2, 4, 5))
    assert wrong_inverse != source  # wrong inverse permutation
    omitted_last_block = interleave_bits(source + (1, 0, 1, 1, 0, 0), 2, 3).bits[:-6]
    assert omitted_last_block != interleave_bits(source + (1, 0, 1, 1, 0, 0), 2, 3).bits
    padded = interleave_bits((1, 0, 1), 2, 2)
    assert padded.valid_length == 3 and padded.padded_length == 4 and padded.pad_count == 1
    # Known one-error witness: the information BER denominator is N=3, not 2*(N+2)=10.
    assert 1 / len((1, 0, 1)) != 1 / len(coding.encode((1, 0, 1)))
