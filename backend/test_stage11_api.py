"""Stage11 experiment endpoint contracts and exact production dataflow checks."""
from fastapi.testclient import TestClient
import pytest

import main
from convolutional_coding import decode_frame, encode_frame
from interleaving import apply_burst_errors, deinterleave_bits, interleave_bits


client = TestClient(main.app)
ENDPOINT = "/api/stage11/experiments"


def post(payload=None):
    return client.post(ENDPOINT, json=payload or {})


def test_valid_experiment_matches_stage10_and_stage11_production_functions():
    payload = {"n_information_bits": 17, "seed": 31, "rows": 2, "columns": 3, "burst_start": 1, "burst_length": 4}
    response = post(payload)
    assert response.status_code == 200
    body = response.json()
    import numpy as np
    information = tuple(int(bit) for bit in np.random.default_rng(31).integers(0, 2, size=17))
    encoded = encode_frame(information)
    interleaved = interleave_bits(encoded.encoded_bits, 2, 3)
    burst = apply_burst_errors(interleaved.bits, 4, start=1)
    restored = deinterleave_bits(burst.bits, len(encoded.encoded_bits), 2, 3)
    decoded = decode_frame(restored, 17)
    coded_errors = [i for i, pair in enumerate(zip(encoded.encoded_bits, restored)) if pair[0] != pair[1]]
    info_errors = [i for i, pair in enumerate(zip(information, decoded.information_bits)) if pair[0] != pair[1]]
    assert body["details"] == {
        "information_bits": list(information), "encoded_bits": list(encoded.encoded_bits),
        "interleaved_bits": list(interleaved.bits), "transmitted_bits": list(burst.bits),
        "deinterleaved_bits": list(restored), "decoded_information_bits": list(decoded.information_bits),
    }
    assert body["interleaver"]["output_sources"] == list(interleaved.output_sources)
    assert body["channel"]["flipped_positions"] == [1, 2, 3, 4]
    assert [body["channel"]["transmission_to_coded_index"][str(i)] for i in range(1, 5)] == [interleaved.output_sources[i] for i in range(1, 5)]
    assert body["results"]["coded_error_indices_after_deinterleave"] == coded_errors
    assert body["results"]["decoded_information_error_indices"] == info_errors
    assert body["results"]["information_error_count"] == len(info_errors)
    assert body["results"]["information_ber_denominator"] == 17
    assert body["results"]["information_ber"] == len(info_errors) / 17


def test_minimum_frame_zero_length_burst_and_padding_burst_are_excluded_from_ber():
    minimal = post({"n_information_bits": 1, "rows": 2, "columns": 4, "burst_start": 0, "burst_length": 0})
    assert minimal.status_code == 200
    assert minimal.json()["lengths"] == {
        "information_bits": 1, "tail_bits": 2, "encoded_bits": 6,
        "valid_interleaved_bits": 6, "transmitted_bits": 8, "padding_bits": 2,
        "decoded_information_bits": 1,
    }
    padding_index = next(i for i, source in enumerate(minimal.json()["interleaver"]["output_sources"]) if source is None)
    padding_burst = post({"n_information_bits": 1, "rows": 2, "columns": 4, "burst_start": padding_index, "burst_length": 1})
    assert padding_burst.status_code == 200
    result = padding_burst.json()
    assert result["channel"]["flipped_count"] == 1
    assert result["results"]["coded_error_count"] == 0
    assert result["results"]["information_ber_denominator"] == 1
    assert result["results"]["information_error_count"] == 0


@pytest.mark.parametrize("payload", [
    {"n_information_bits": 0}, {"n_information_bits": 4097}, {"n_information_bits": 1.5},
    {"rows": 0}, {"columns": -1}, {"rows": 1024, "columns": 1025},
    {"burst_start": -1}, {"burst_length": -1}, {"burst_start": 99999},
    {"n_information_bits": 1, "rows": 2, "columns": 4, "burst_start": 7, "burst_length": 2},
    {"n_information_bits": 1, "rows": 2, "columns": 4, "burst_length": 9},
    {"seed": -1}, {"seed": True}, {"unknown": 1},
])
def test_invalid_dimensions_lengths_indices_and_limits_return_controlled_422(payload):
    response = post(payload)
    assert response.status_code == 422, payload
    assert response.json().get("detail")
    assert "Traceback" not in response.text


def test_stage11_bad_json_content_type_uses_project_error_contract():
    response = client.post(ENDPOINT, content='{"n_information_bits":8}')
    assert response.status_code == 422
    assert response.json()["detail"]


def test_internal_failure_hides_details(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret implementation detail")

    monkeypatch.setattr(main, "stage11_interleave_bits", fail)
    response = post({"n_information_bits": 5})
    assert response.status_code == 500
    assert response.json()["detail"] == "Stage11 experiment could not be completed. Please retry."
    assert "secret implementation" not in response.text
