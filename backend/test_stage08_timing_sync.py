import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app, stage08_challenge_cache
from timing_sync import create_experiment, ber_for_phase, rrc_taps

client = TestClient(app)


def test_signal_generation_is_reproducible_and_bounded():
    first = create_experiment(seed=9001, timing_offset_samples=-4, eb_n0_db=8, n_payload_symbols=512)
    second = create_experiment(seed=9001, timing_offset_samples=-4, eb_n0_db=8, n_payload_symbols=512)
    assert np.array_equal(first["payload_bits"], second["payload_bits"])
    assert np.array_equal(first["rx_waveform"], second["rx_waveform"])
    assert np.array_equal(first["matched"], second["matched"])
    assert first["initial_measurement"] == second["initial_measurement"]


@pytest.mark.parametrize("kwargs", [
    {"timing_offset_samples": True}, {"timing_offset_samples": 8},
    {"eb_n0_db": float("nan")}, {"n_payload_symbols": 511},
])
def test_model_rejects_invalid_signal_parameters(kwargs):
    values = {"seed": 1, "timing_offset_samples": 0, "eb_n0_db": 8, "n_payload_symbols": 512}
    values.update(kwargs)
    with pytest.raises(ValueError):
        create_experiment(**values)


def test_ber_uses_identical_payload_positions_and_denominator_for_every_phase():
    exp = create_experiment(seed=18, timing_offset_samples=3, eb_n0_db=8, n_payload_symbols=512)
    results = [ber_for_phase(exp["matched"], exp["payload_bits"], exp["payload_start_symbol"], p,
                             exp["group_delay_samples"]) for p in (-3, 0, 3)]
    assert {item["n_compared"] for item in results} == {512}
    assert {(item["payload_symbol_start"], item["payload_symbol_end_exclusive"]) for item in results} == {
        (68, 580)
    }
    assert all(item["n_errors"] <= item["n_compared"] for item in results)


def test_api_hides_challenge_answer_and_gates_state_machine():
    stage08_challenge_cache.clear()
    created = client.post("/api/stage08/challenges", json={"mode": "challenge", "eb_n0_db": 8,
                                                           "n_payload_symbols": 512})
    assert created.status_code == 200
    body = created.json()
    cid = body["challenge_id"]
    assert not ({"seed", "timing_offset_samples", "actual_fault", "reference_ber", "payload_bits"} & body.keys())
    assert "timing_offset_samples" not in str(body)
    assert client.post("/api/stage08/challenges/compensate", json={"challenge_id": cid,
                                                                    "compensation_samples": 0}).status_code == 409
    assert client.get(f"/api/stage08/challenges/{cid}/feedback").status_code == 409
    assert client.get(f"/api/stage08/challenges/{cid}/measurement").status_code == 200
    challenge = stage08_challenge_cache[cid]
    correct_fault = "timing_offset" if challenge["timing_offset_samples"] else "no_timing_offset"
    wrong_fault = "no_timing_offset" if correct_fault == "timing_offset" else "timing_offset"
    wrong = client.post("/api/stage08/challenges/diagnosis", json={"challenge_id": cid,
                                                                    "suspected_fault": wrong_fault})
    assert wrong.status_code == 200 and wrong.json()["correct"] is False
    assert "timing_offset_samples" not in str(wrong.json())
    right = client.post("/api/stage08/challenges/diagnosis", json={"challenge_id": cid,
                                                                    "suspected_fault": correct_fault})
    assert right.status_code == 200 and right.json()["correct"] is True
    compensation = client.post("/api/stage08/challenges/compensate", json={"challenge_id": cid,
        "compensation_samples": challenge["initial_measurement"]["phase_samples"]})
    assert compensation.status_code == 200
    before, after = compensation.json()["before"], compensation.json()["after"]
    assert before["n_compared"] == after["n_compared"] == 512
    assert before["payload_symbol_start"] == after["payload_symbol_start"]
    assert before["payload_symbol_end_exclusive"] == after["payload_symbol_end_exclusive"]
    feedback = client.get(f"/api/stage08/challenges/{cid}/feedback")
    assert feedback.status_code == 200
    assert feedback.json()["actual_fault"]["timing_offset_samples"] == challenge["timing_offset_samples"]


def test_api_rejects_bool_float_out_of_range_and_challenge_truth_inputs():
    assert client.post("/api/stage08/challenges", json={"mode": "guided", "timing_offset_samples": True}).status_code == 422
    assert client.post("/api/stage08/challenges", json={"mode": "guided", "timing_offset_samples": 1.0}).status_code == 422
    assert client.post("/api/stage08/challenges", json={"mode": "guided", "timing_offset_samples": 8}).status_code == 422
    assert client.post("/api/stage08/challenges", json={"mode": "challenge", "seed": 7}).status_code == 422
    assert client.post("/api/stage08/challenges", json={"mode": "guided", "timing_offset_samples": 0,
                                                         "seed": 7, "n_payload_symbols": 512}).status_code == 200


def test_rrc_parameters_and_sampling_reject_invalid_values():
    assert len(rrc_taps()) == 129
    for args in ({"rolloff": 0}, {"rolloff": float("inf")}, {"span_symbols": 7},
                 {"samples_per_symbol": True}):
        with pytest.raises(ValueError):
            rrc_taps(**args)
