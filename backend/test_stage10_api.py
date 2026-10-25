"""API contract checks for the Stage10 production experiment endpoint."""

from fastapi.testclient import TestClient

import main
from convolutional_coding import run_experiment


client = TestClient(main.app)
ENDPOINT = "/api/stage10/experiments"


def request(payload=None):
    return client.post(ENDPOINT, json=payload or {})


def test_valid_request_returns_auditable_result_from_production_core():
    response = request({"n_information_bits": 17, "eb_n0_db": 3.5, "seed": 81})
    assert response.status_code == 200
    data = response.json()
    expected = run_experiment(17, 3.5, 81)
    assert data["parameters"] == {"n_information_bits": 17, "eb_n0_db": 3.5, "seed": 81, "include_details": False}
    assert data["results"]["uncoded_information"] == {"errors": expected.uncoded_errors, "compared": 17, "ber": expected.uncoded_ber}
    assert data["results"]["coded_channel"]["errors"] == expected.coded_channel_errors
    assert data["results"]["decoded_information"] == {
        "errors": expected.decoded_information_errors,
        "compared": 17,
        "ber": expected.decoded_information_ber,
        "correctly_recovered": expected.decoded_information_errors == 0,
        "decoded_tail_bits": [0, 0],
        "tail_counted": False,
    }
    assert data["energy"]["noise_variance"] == expected.noise_variance
    assert data["lengths"] == {
        "information_bits": 17,
        "tail_bits": 2,
        "encoded_bits": 38,
        "encoded_symbols": 38,
        "decoded_information_bits": 17,
        "effective_frame_rate": 17 / 38,
    }
    assert data["details"]["truncated"] is False
    assert data["details"]["information_bits"] == list(expected.information_bits)


def test_same_seed_replays_api_results_and_details():
    payload = {"n_information_bits": 32, "eb_n0_db": 2, "seed": 123, "include_details": True}
    first, second = request(payload), request(payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_details_are_bounded_and_default_preview_is_finite():
    default = request({"n_information_bits": 512}).json()
    assert default["details"]["truncated"] is True
    assert default["details"]["window_information_bits"] == 64
    assert len(default["details"]["information_bits"]) == 64
    assert default["details"]["window_encoded_bits"] == 128
    assert len(default["details"]["encoded_bits"]) == 128
    full = request({"n_information_bits": 256, "include_details": True}).json()
    assert full["details"]["included"] is True
    assert len(full["details"]["information_bits"]) == 256


def test_minimum_and_maximum_frame_sizes_keep_lengths_consistent():
    for n in (1, 4096):
        response = request({"n_information_bits": n})
        assert response.status_code == 200
        body = response.json()
        assert body["lengths"]["encoded_bits"] == 2 * (n + 2)
        assert body["lengths"]["decoded_information_bits"] == n
        assert body["results"]["decoded_information"]["compared"] == n


def test_invalid_parameters_and_oversized_details_are_controlled_4xx():
    invalid = [
        {"n_information_bits": 0},
        {"n_information_bits": 4097},
        {"n_information_bits": 1.5},
        {"eb_n0_db": 31},
        {"eb_n0_db": float("nan")},
        {"seed": -1},
        {"seed": True},
        {"unknown": "value"},
        {"n_information_bits": 257, "include_details": True},
    ]
    for payload in invalid:
        response = request(payload)
        assert response.status_code == 422, payload
        assert "Traceback" not in response.text


def test_missing_json_content_type_is_rejected_by_project_middleware():
    response = client.post(ENDPOINT, content='{"n_information_bits":4}')
    assert response.status_code == 422
    assert response.json()["detail"]


def test_internal_error_does_not_leak_exception_details(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret internal implementation detail")

    monkeypatch.setattr(main, "run_stage10_experiment", fail)
    response = request({"n_information_bits": 3})
    assert response.status_code == 500
    assert response.json()["detail"] == "Stage10 experiment could not be completed. Please retry."
    assert "secret internal" not in response.text
