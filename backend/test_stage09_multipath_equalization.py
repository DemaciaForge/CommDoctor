from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


def test_stage09_create_estimate_equalize_and_feedback_use_same_payload_contract():
    created = client.post("/api/stage09/experiments", json={
        "mode": "guided", "seed": 2026, "eb_n0_db": 8, "n_payload_symbols": 128,
    })
    assert created.status_code == 200
    body = created.json()
    experiment_id = body["experiment_id"]
    assert body["layout"]["payload_end_symbol_exclusive"] > body["layout"]["payload_start_symbol"]
    assert body["raw_ber"]["n_compared"] == 128
    assert len(body["layout"]["payload_sample_indices"]) == 128
    measured = client.get(f"/api/stage09/experiments/{experiment_id}/estimate")
    assert measured.status_code == 200
    assert measured.json()["training_rows"] == 60
    mmse = client.post(f"/api/stage09/experiments/{experiment_id}/equalize", json={"algorithm": "mmse"})
    zf = client.post(f"/api/stage09/experiments/{experiment_id}/equalize", json={"algorithm": "zf"})
    assert mmse.status_code == zf.status_code == 200
    assert mmse.json()["n_compared"] == zf.json()["n_compared"] == body["raw_ber"]["n_compared"]
    assert mmse.json()["sample_indices"] == zf.json()["sample_indices"] == body["raw_ber"]["sample_indices"]
    feedback = client.get(f"/api/stage09/experiments/{experiment_id}/feedback")
    assert feedback.status_code == 200
    assert feedback.json()["effective_payload"]["n_compared"] == 128


def test_stage09_challenge_does_not_leak_seed_or_true_channel_before_feedback():
    created = client.post("/api/stage09/experiments", json={"mode": "challenge", "eb_n0_db": 8, "n_payload_symbols": 128})
    assert created.status_code == 200
    body = created.json()
    assert "seed" not in body
    assert "path_gains" not in body["parameters"]
    assert "path_delays_samples" not in body["parameters"]
    assert "normalized_gains" not in body["channel"]


def test_stage09_rejects_illegal_inputs_and_feedback_order():
    assert client.post("/api/stage09/experiments", json={"mode": "guided", "seed": True, "n_payload_symbols": 128}).status_code == 422
    assert client.post("/api/stage09/experiments", json={"mode": "guided", "seed": 1, "n_payload_symbols": 128,
                                                         "path_delays_samples": [0, 1], "path_gains": [1, .7]}).status_code == 422
    missing = client.get("/api/stage09/experiments/no-such-id/feedback")
    assert missing.status_code == 404
    created = client.post("/api/stage09/experiments", json={"mode": "guided", "seed": 2, "n_payload_symbols": 128})
    assert client.get(f"/api/stage09/experiments/{created.json()['experiment_id']}/feedback").status_code == 409
