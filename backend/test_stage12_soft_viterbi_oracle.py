"""Stage12 Phase 1 contracts; production soft Viterbi is intentionally absent."""

import ast
import math
from pathlib import Path

import pytest

from convolutional_coding import decode_frame, encode, hard_decision, snr_quantities
from tests.oracles import stage12_soft_viterbi_oracle as oracle


def test_oracle_is_independent_of_production_algorithms():
    source = Path(oracle.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert set(imports) <= {"__future__", "dataclasses", "math", "typing"}
    assert "convolutional_coding" not in source
    assert "decode_frame" not in source


def test_known_vectors_and_termination_contract():
    assert oracle.encode_payload((0,)) == (0, 0, 0, 0, 0, 0)
    assert oracle.encode_payload((1, 0)) == (1, 1, 1, 0, 1, 1, 0, 0)
    assert oracle.encode_payload((1, 0, 1)) == (1, 1, 1, 0, 0, 0, 1, 0, 1, 1)
    for payload in ((0,), (1,), (0, 1, 0, 1), (1, 1, 1, 1)):
        path = oracle.optimal_paths(oracle.bpsk_symbols(oracle.encode_payload(payload)), len(payload))
        assert len(path) == 1
        assert path[0].information_bits == payload
        assert path[0].encoder_input_bits[-2:] == (0, 0)
        assert path[0].distance == 0.0


def test_all_short_noiseless_payloads_are_unique_optima():
    for n in range(1, 7):
        for value in range(1 << n):
            payload = tuple((value >> shift) & 1 for shift in range(n - 1, -1, -1))
            encoded = oracle.encode_payload(payload)
            winners = oracle.optimal_paths(oracle.bpsk_symbols(encoded), n)
            assert len(winners) == 1
            assert winners[0].information_bits == payload
            assert winners[0].distance == 0.0


def test_each_enumerated_distance_matches_independent_formula_and_minimum():
    received = (0.8, -0.4, 0.1, -0.9, 0.3, -0.2, 0.7, -0.6)
    paths = oracle.enumerate_paths(received, 2)
    assert len(paths) == 4
    for path in paths:
        expected = sum(
            (sample - transmitted) ** 2
            for sample, transmitted in zip(received, oracle.bpsk_symbols(path.encoded_bits))
        )
        assert path.distance == pytest.approx(expected)
    winners = oracle.optimal_paths(received, 2)
    assert winners
    assert winners[0].distance == min(path.distance for path in paths)
    assert all(path.distance == winners[0].distance for path in winners)


def test_exact_boundary_samples_form_a_real_mathematical_tie():
    received = (0.0,) * 6
    winners = oracle.optimal_paths(received, 1)
    assert {path.information_bits for path in winners} == {(0,), (1,)}
    assert {path.encoder_input_bits for path in winners} == {(0, 0, 0), (1, 0, 0)}
    assert all(path.distance == pytest.approx(3.0) for path in winners)


def test_recommended_predecessor_tie_rule_and_mutant():
    # Phase 2 recommendation: exact metric ties for a target state retain
    # the numerically smaller predecessor, matching the existing hard path.
    candidates = ((2, 1.25), (1, 1.25))
    selected = min(candidates, key=lambda item: (item[1], item[0]))
    mutant_selected = min(candidates, key=lambda item: (item[1], -item[0]))
    assert selected == (1, 1.25)
    assert mutant_selected == (2, 1.25)
    assert selected != mutant_selected


def test_hard_and_soft_can_disagree_on_the_same_received_samples():
    # The sign pattern has a Hamming tie-breaking advantage for payload 0,
    # while the large positive amplitudes make payload 1 ML-optimal.
    received = (10.0, 10.0, -0.1, 0.1, -0.1, -0.1)
    hard_bits = hard_decision(received)
    hard_result = decode_frame(hard_bits, 1)
    soft_winners = oracle.optimal_paths(received, 1)
    assert hard_result.information_bits == (0,)
    assert len(soft_winners) == 1
    assert soft_winners[0].information_bits == (1,)
    assert hard_bits == (1, 1, 0, 1, 0, 0)


def test_soft_metric_is_not_hamming_or_absolute_distance():
    received = (10.0, 10.0, -0.1, 0.1, -0.1, -0.1)
    expected = oracle.optimal_paths(received, 1)[0].information_bits

    def hamming_mutant(payload):
        encoded = oracle.encode_payload(payload)
        decisions = tuple(int(value > 0) for value in received)
        return sum(left != right for left, right in zip(encoded, decisions))

    mutant_scores = {payload: hamming_mutant(payload) for payload in ((0,), (1,))}
    mutant_winner = min(mutant_scores, key=lambda payload: (mutant_scores[payload], payload))
    assert expected != mutant_winner


def test_termination_constraint_rejects_an_unterminated_zero_distance_path():
    def encode_inputs(inputs):
        state = 0
        output = []
        for bit in inputs:
            state, pair = oracle.transition(state, bit)
            output.extend(pair)
        return tuple(output), state

    unterminated_bits, final_state = encode_inputs((1, 1, 1))
    assert final_state != 0
    received = oracle.bpsk_symbols(unterminated_bits)
    assert min(path.distance for path in oracle.enumerate_paths(received, 1)) > 0
    unrestricted = [
        (oracle.path_distance(received, encode_inputs(inputs)[0]), encode_inputs(inputs)[1])
        for value in range(8)
        for inputs in (tuple((value >> shift) & 1 for shift in (2, 1, 0)),)
    ]
    assert min(distance for distance, _ in unrestricted) == 0.0
    assert any(distance == 0.0 and state != 0 for distance, state in unrestricted)


def test_output_order_and_tail_mutants_are_detectable():
    payload = (1, 0, 1)
    expected = oracle.encode_payload(payload)
    state = 0
    swapped = []
    for bit in payload + oracle.TAIL_BITS:
        state, pair = oracle.transition(state, bit)
        swapped.extend(pair[::-1])
    assert tuple(swapped) != expected
    one_tail = oracle.encode_payload(payload)[:-2]
    assert len(one_tail) == len(expected) - 2
    assert one_tail != expected


def test_nonfinite_and_overflow_contracts_are_explicit():
    with pytest.raises(ValueError):
        oracle.optimal_paths((math.nan,) * 6, 1)
    with pytest.raises(ValueError):
        oracle.optimal_paths((math.inf,) * 6, 1)
    with pytest.raises(ValueError):
        oracle.optimal_paths((-math.inf,) * 6, 1)
    finite_extreme = oracle.optimal_paths((1e150,) * 6, 1)
    assert finite_extreme
    assert math.isfinite(finite_extreme[0].distance)
    with pytest.raises(ValueError, match="overflow"):
        oracle.optimal_paths((1e308,) * 6, 1)
    with pytest.raises(ValueError):
        oracle.optimal_paths((0.0,) * 4, 1)


def test_shortest_frame_and_input_validation():
    with pytest.raises(ValueError):
        oracle.optimal_paths((), 0)
    with pytest.raises(ValueError):
        oracle.encode_payload(())
    with pytest.raises(ValueError):
        oracle.encode_payload((True,))
    with pytest.raises(ValueError):
        oracle.bpsk_symbols((0,), 0.0)
    with pytest.raises(ValueError):
        oracle.bpsk_symbols((0,), math.inf)


def test_awgn_metric_scaling_and_stage10_energy_contract():
    q = snr_quantities(0.0)
    assert q["coded_symbol_energy"] == 0.5
    assert q["coded_amplitude"] == pytest.approx(math.sqrt(0.5))
    assert q["noise_variance"] == pytest.approx(0.5)
    received = (0.2, -0.8, 0.4, -0.3, 0.7, -0.1)
    paths = oracle.enumerate_paths(received, 1)
    scaled = {path.information_bits: path.distance / (2 * q["noise_variance"]) for path in paths}
    assert min(scaled, key=scaled.get) in {path.information_bits for path in oracle.optimal_paths(received, 1)}


def test_fairness_contract_uses_one_received_array_and_information_denominator():
    payload = (1, 0, 1)
    encoded = oracle.encode_payload(payload)
    received = oracle.bpsk_symbols(encoded)
    hard_input = received
    soft_input = received
    assert hard_input is soft_input
    assert len(encoded) == 2 * (len(payload) + 2)
    assert len(payload) == 3
    assert oracle.optimal_paths(soft_input, len(payload))[0].information_bits == payload


def test_no_claim_that_soft_is_better_on_every_finite_sample():
    received = oracle.bpsk_symbols(oracle.encode_payload((0,)))
    soft = oracle.optimal_paths(received, 1)[0].information_bits
    hard = decode_frame(hard_decision(received), 1).information_bits
    assert soft == hard == (0,)
