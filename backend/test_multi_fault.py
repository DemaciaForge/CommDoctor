"""Stage05 multi-fault challenge and unified-model acceptance tests."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
import main
from frequency_offset import calculate_bpsk_ber
from multi_fault import FAULT_SCENARIOS, apply_compensation, estimate_multi_fault, simulate_multi_fault


client = TestClient(main.app)


@pytest.mark.parametrize("scenario,dc,epsilon", [
    ("none", 0.0, 0.0), ("dc_offset", 0.35, 0.0),
    ("frequency_offset", 0.0, 0.02), ("both", 0.35, 0.02),
])
def test_unified_model_and_ordered_compensation(scenario, dc, epsilon):
    experiment = simulate_multi_fault(seed=42, scenario=scenario, dc_offset=dc, epsilon=epsilon)
    measurement = estimate_multi_fault(experiment["received"])
    assert abs(measurement["dc_hat"] - dc) < 0.04
    assert abs(measurement["epsilon_hat"] - epsilon) < 0.001
    assert np.array_equal(
        apply_compensation(experiment["received"], measurement["dc_hat"], measurement["epsilon_hat"], "both"),
        (experiment["received"] - measurement["dc_hat"])
        * np.exp(-1j * 2 * np.pi * measurement["epsilon_hat"] * np.arange(experiment["n_symbols"])),
    )
    if scenario == "both":
        assert calculate_bpsk_ber(experiment["bits"], apply_compensation(experiment["received"], measurement["dc_hat"], measurement["epsilon_hat"], "both"))["n_errors"] < experiment["before"]["n_errors"]


def _force_scenario(monkeypatch, scenario):
    def choice(values):
        if tuple(values) == FAULT_SCENARIOS:
            return scenario
        return values[0]
    monkeypatch.setattr(main.secrets, "choice", choice)
    monkeypatch.setattr(main.secrets, "randbits", lambda _: 42)


@pytest.mark.parametrize("scenario", FAULT_SCENARIOS)
def test_api_hides_answers_and_completes_all_four_scenarios(monkeypatch, scenario):
    _force_scenario(monkeypatch, scenario)
    created = client.post("/api/stage05/challenges")
    assert created.status_code == 200
    data = created.json(); cid = data["challenge_id"]
    for hidden in ("scenario", "dc_offset", "epsilon", "seed", "actual_fault", "reference"):
        assert hidden not in data
    assert "mean_i" in data["signal"] and data["before"]["n_errors"] >= 0
    measured = client.get(f"/api/stage05/challenges/{cid}/measurement")
    assert measured.status_code == 200
    m = measured.json(); assert math.isfinite(m["dc_hat"]) and math.isfinite(m["epsilon_hat"])
    wrong = "none" if scenario != "none" else "both"
    assert client.post("/api/stage05/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": wrong}).json()["correct"] is False
    right = client.post("/api/stage05/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": scenario})
    assert right.status_code == 200 and right.json()["correct"] is True
    result = client.post("/api/stage05/challenges/compensate", json={"challenge_id": cid, "mode": "both", "dc_hat": m["dc_hat"], "epsilon_hat": m["epsilon_hat"]})
    assert result.status_code == 200
    assert result.json()["after"]["ber"] == result.json()["after"]["n_errors"] / data["n_symbols"]
    feedback = client.get(f"/api/stage05/challenges/{cid}/feedback")
    assert feedback.status_code == 200 and feedback.json()["diagnosis"]["correct"] is True


def test_api_supports_independent_compensation_stages_and_gates(monkeypatch):
    _force_scenario(monkeypatch, "both")
    data = client.post("/api/stage05/challenges").json(); cid = data["challenge_id"]
    assert client.post("/api/stage05/challenges/compensate", json={"challenge_id": cid, "mode": "both", "dc_hat": 0, "epsilon_hat": 0}).status_code == 409
    m = client.get(f"/api/stage05/challenges/{cid}/measurement").json()
    client.post("/api/stage05/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "both"})
    for mode in ("dc", "frequency", "both"):
        response = client.post("/api/stage05/challenges/compensate", json={"challenge_id": cid, "mode": mode, "dc_hat": m["dc_hat"], "epsilon_hat": m["epsilon_hat"]})
        assert response.status_code == 200 and mode in response.json()["all_results"]
    assert set(client.get(f"/api/stage05/challenges/{cid}/feedback").json()["ber"]["stages"]) == {"dc", "frequency", "both"}


@pytest.mark.parametrize("payload", [
    {"mode": "bad", "dc_hat": 0, "epsilon_hat": 0},
    {"mode": "both", "dc_hat": "0", "epsilon_hat": 0},
    {"mode": "both", "dc_hat": 0, "epsilon_hat": 0.25},
    {"mode": "both", "dc_hat": 0, "epsilon_hat": float("nan")},
])
def test_api_rejects_invalid_compensation(monkeypatch, payload):
    _force_scenario(monkeypatch, "none")
    data = client.post("/api/stage05/challenges").json(); cid = data["challenge_id"]
    m = client.get(f"/api/stage05/challenges/{cid}/measurement").json()
    client.post("/api/stage05/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "none"})
    payload = {**payload, "challenge_id": cid}
    assert client.post("/api/stage05/challenges/compensate", json=payload).status_code == 422
