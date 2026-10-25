"""Production Stage10 tests against the independent Phase 1 oracle."""

from itertools import product

import pytest

from convolutional_coding import (
    CODE_RATE,
    TAIL_BITS,
    ber,
    decode_frame,
    encode,
    encode_frame,
    hard_decision,
    run_experiment,
    snr_quantities,
    transition,
    viterbi_decode,
)
from tests.oracles import stage10_convolutional_oracle as oracle


@pytest.mark.parametrize("bits", [(0,), (1,), (1, 0), (1, 1, 1), (1, 0, 1, 0), (0, 1, 0, 1, 0)])
def test_production_encoder_matches_independent_oracle(bits):
    assert encode(bits) == oracle.encode(bits)
    frame = encode_frame(bits)
    assert frame.encoder_input_bits == bits + TAIL_BITS
    assert len(frame.encoded_bits) == 2 * (len(bits) + 2)


@pytest.mark.parametrize("n", range(1, 7))
def test_all_short_codewords_decode_without_noise(n):
    for bits in product((0, 1), repeat=n):
        encoded = encode(bits)
        assert viterbi_decode(encoded, n) == bits
        decoded = decode_frame(encoded, n)
        assert decoded.decoder_input_bits == bits + TAIL_BITS
        assert decoded.final_state == 0
        assert decoded.path_metric == 0


def test_viterbi_matches_exhaustive_optimum_and_declared_tie_rule():
    for n in range(1, 5):
        for bits in product((0, 1), repeat=n):
            received = list(encode(bits))
            received[(n * 3) % len(received)] ^= 1
            expected = oracle.optimal_paths(received, n)
            decoded = viterbi_decode(received, n)
            assert decoded in {path.information for path in expected}
    tied = (0, 0, 0, 0, 0, 1, 1, 1)
    assert oracle.optimal_paths(tied, 2)
    assert viterbi_decode(tied, 2) == (0, 0)


def test_ber_counts_information_only_and_preserves_real_denominator():
    assert ber((1, 0, 1, 1, 0), (1, 1, 1, 0, 0)) == {"errors": 2, "compared": 5, "ber": 0.4}
    result = run_experiment(1, 100.0, 7, information_bits=(1,))
    assert result.information_bit_count == 1
    assert result.encoded_bit_count == 6
    assert result.decoded_information_length == 1
    assert result.decoded_information_ber == 0.0


def test_energy_rate_and_noise_contract():
    quantities = snr_quantities(0.0)
    assert quantities["noise_variance"] == 0.5
    assert quantities["noise_std"] ** 2 == pytest.approx(quantities["noise_variance"])
    assert quantities["coded_symbol_energy"] == CODE_RATE
    assert quantities["coded_amplitude"] == pytest.approx(2 ** -0.5)
    result = run_experiment(5, 6.0, 3, information_bits=(0, 1, 0, 1, 1))
    assert result.noise_variance == pytest.approx(1 / (2 * 10 ** 0.6))
    assert result.encoded_symbol_count == 2 * (result.information_bit_count + 2)


def test_seed_replays_full_experiment_and_streams_are_independent_lengths():
    one = run_experiment(4, 4.0, 42)
    two = run_experiment(4, 4.0, 42)
    assert one == two
    other = run_experiment(4, 4.0, 43)
    assert other != one
    assert len(one.uncoded_received) == 4
    assert len(one.coded_received) == 12


def test_hard_decision_and_input_boundaries_are_controlled():
    assert hard_decision((-1.0, 0.0, 1.0)) == (0, 0, 1)
    for invalid in ((0, 2), (True,), (0.0,), (), "01"):
        with pytest.raises(ValueError):
            encode(invalid)
    for invalid in ((0, 1), (True,), (), (0, 1, 0)):
        with pytest.raises(ValueError):
            viterbi_decode(invalid, 1)
    for invalid in ((True,), (), (float("nan"),), ("0",)):
        with pytest.raises(ValueError):
            hard_decision(invalid)
    for invalid in (True, 0, -1, 1.0):
        with pytest.raises(ValueError):
            run_experiment(invalid, 0.0, 1)
    for invalid in (-1, 2**32, True, 1.0):
        with pytest.raises(ValueError):
            run_experiment(1, 0.0, invalid)


def test_transition_trellis_is_the_locked_four_state_contract():
    expected = {
        (0, 0): (0, (0, 0)), (0, 1): (2, (1, 1)),
        (1, 0): (0, (1, 1)), (1, 1): (2, (0, 0)),
        (2, 0): (1, (1, 0)), (2, 1): (3, (0, 1)),
        (3, 0): (1, (0, 1)), (3, 1): (3, (1, 0)),
    }
    assert {key: transition(*key) for key in expected} == expected
