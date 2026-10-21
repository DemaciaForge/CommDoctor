"""Stage03 challenge workflow tests: real simulation, hidden answer, gated diagnosis and repair."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from main import app, challenge_cache


client = TestClient(app)


def create_challenge():
    response = client.post("/api/challenges")
    assert response.status_code == 200
    return response.json()


def test_challenge_uses_live_data_but_hides_fault_and_answer():
    challenge = create_challenge()
    assert challenge["status"] == "observe"
    assert len(challenge["samples"]["rx_with_fault"]) == 1000
    assert len(challenge["samples"]["tx_symbols"]) == 1000
    assert challenge["with_fault"]["n_errors"] >= 0
    assert challenge["with_fault"]["ber"] == challenge["with_fault"]["n_errors"] / challenge["n_bits"]
    for private_field in ("dc_offset", "diagnosis", "repaired", "seed", "suggested_threshold"):
        assert private_field not in challenge
    assert challenge["challenge_id"] in challenge_cache


def test_diagnosis_requires_measurement_and_wrong_answer_can_be_retried():
    challenge = create_challenge()
    cid = challenge["challenge_id"]

    blocked = client.post("/api/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "dc_offset"})
    assert blocked.status_code == 409

    measurement = client.get(f"/api/challenges/{cid}/measurement")
    assert measurement.status_code == 200
    evidence = measurement.json()
    assert evidence["n_samples"] == 10000
    assert abs(evidence["rx_mean"]) > evidence["threshold_3sigma"]
    assert "dc_offset" not in evidence
    assert "diagnosis" not in evidence

    wrong = client.post("/api/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "no_fault"})
    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert "dc_offset" not in wrong.json()
    assert client.get(f"/api/challenges/{cid}/feedback").status_code == 409

    correct = client.post("/api/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "dc_offset"})
    assert correct.status_code == 200
    assert correct.json()["correct"] is True


def test_repair_is_gated_and_matches_existing_threshold_calculation():
    challenge = create_challenge()
    cid = challenge["challenge_id"]
    blocked = client.post("/api/challenges/repair", json={"challenge_id": cid, "threshold": 0.7})
    assert blocked.status_code == 409
    client.get(f"/api/challenges/{cid}/measurement")
    client.post("/api/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "dc_offset"})

    result = client.post("/api/challenges/repair", json={"challenge_id": cid, "threshold": 0.8})
    assert result.status_code == 200
    data = result.json()
    assert data["after"]["threshold"] == 0.8
    assert data["after"]["ber"] == data["after"]["n_errors"] / challenge["n_bits"]
    assert data["improved"] is (data["after"]["n_errors"] < data["before"]["n_errors"])

    feedback = client.get(f"/api/challenges/{cid}/feedback")
    assert feedback.status_code == 200
    report = feedback.json()
    assert report["diagnosis_correct"] is True
    assert report["actual_fault"]["dc_offset"] in (-0.8, 0.8)
    assert report["repair"]["after"] == data["after"]
    assert report["repair"]["before"] == data["before"]
    assert report["repair"]["ideal_threshold_result"]["threshold"] == report["evidence"]["rx_mean"]


def test_challenge_invalid_inputs_and_expired_ids_are_rejected():
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/challenges/{missing}/measurement").status_code == 404
    assert client.post("/api/challenges/diagnosis", json={"challenge_id": missing, "suspected_fault": "noise"}).status_code == 422
    assert client.post("/api/challenges/repair", json={"challenge_id": missing, "threshold": 99}).status_code == 422
