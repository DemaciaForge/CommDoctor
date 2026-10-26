"""Stage10 multi-Eb/N0 sweep contracts, through production and HTTP APIs."""

import main
from convolutional_coding import (
    MAX_SWEEP_TOTAL_INFORMATION_BITS,
    eb_n0_scan_points,
    run_eb_n0_sweep,
    run_experiment,
)
from fastapi.testclient import TestClient


client = TestClient(main.app)
ENDPOINT = "/api/stage10/ber-sweep"


def test_scan_grid_is_inclusive_sorted_and_uses_decimal_steps():
    assert eb_n0_scan_points(0, 1, 0.2) == (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    assert eb_n0_scan_points(-2, 2, 2) == (-2.0, 0.0, 2.0)


def test_scan_grid_rejects_invalid_ranges_and_point_limits():
    for args in ((2, 2, 1), (2, 1, 1), (-11, 1, 1), (0, 1, 0), (0, 1, 0.3), (0, 16, 1)):
        try:
            eb_n0_scan_points(*args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid scan grid rejection: {args}")


def test_sweep_replays_and_reports_independent_payload_noise_design():
    args = (0, 4, 2, 256, 991)
    first = run_eb_n0_sweep(*args)
    assert first == run_eb_n0_sweep(*args)
    assert first["sampling"]["design"] == "independent_payload_and_noise_per_snr"
    assert first["sampling"]["repetitions_per_point"] == 1
    assert [point["eb_n0_db"] for point in first["points"]] == [0.0, 2.0, 4.0]
    assert len({point["seed"] for point in first["points"]}) == 3


def test_each_point_matches_production_experiment_denominators_and_noise():
    response = client.post(ENDPOINT, json={"start_db": 0, "stop_db": 4, "step_db": 2, "n_information_bits": 37, "seed": 55})
    assert response.status_code == 200
    body = response.json()
    assert body["parameters"]["total_information_bits"] == 111
    assert body["code"] == {"constraint_length": 3, "generators_octal": [7, 5], "output_order": ["g0", "g1"], "rate": 0.5, "tail_bits": [0, 0]}
    for point in body["points"]:
        expected = run_experiment(37, point["eb_n0_db"], point["seed"])
        assert point["noise_variance"] == expected.noise_variance
        assert point["uncoded_information"] == {"errors": expected.uncoded_errors, "compared": 37, "ber": expected.uncoded_ber}
        assert point["coded_channel"] == {"errors": expected.coded_channel_errors, "compared": 78, "ber": expected.coded_channel_ber}
        assert point["decoded_information"] == {"errors": expected.decoded_information_errors, "compared": 37, "ber": expected.decoded_information_ber}
        assert point["coded_channel"]["compared"] != point["decoded_information"]["compared"]
        assert point["noise_variance"] == 1 / (2 * 10 ** (point["eb_n0_db"] / 10))


def test_http_reproducibility_zero_errors_and_controlled_validation():
    payload = {"start_db": 28, "stop_db": 30, "step_db": 2, "n_information_bits": 16, "seed": 7}
    first = client.post(ENDPOINT, json=payload)
    second = client.post(ENDPOINT, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    zero_seen = False
    for point in first.json()["points"]:
        for key in ("uncoded_information", "coded_channel", "decoded_information"):
            measure = point[key]
            assert measure["ber"] == measure["errors"] / measure["compared"]
            if measure["errors"] == 0:
                assert measure["ber"] == 0
                zero_seen = True
    assert zero_seen
    invalid = [
        {"start_db": 0, "stop_db": 0, "step_db": 1},
        {"start_db": 0, "stop_db": 1, "step_db": 0.3},
        {"start_db": -11},
        {"start_db": 0, "stop_db": 16, "step_db": 1},
        {"n_information_bits": 4097},
        {"n_information_bits": True},
        {"start_db": 0, "stop_db": 8, "step_db": 1, "n_information_bits": 4096},
        {"seed": -1},
        {"unknown": 1},
    ]
    for invalid_payload in invalid:
        response = client.post(ENDPOINT, json=invalid_payload)
        assert response.status_code == 422, (invalid_payload, response.text)
        assert "Traceback" not in response.text


def test_total_computation_cap_is_explicit():
    assert MAX_SWEEP_TOTAL_INFORMATION_BITS == 32768
    rejected = client.post(ENDPOINT, json={"start_db": 0, "stop_db": 8, "step_db": 1, "n_information_bits": 4096})
    assert rejected.status_code == 422
    assert "at most 32768" in str(rejected.json()["detail"])
