"""Deterministic numerical and API acceptance for Stage04 frequency-offset experiments."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

import main
from frequency_offset import (
    calculate_bpsk_ber,
    compensate_bpsk_frequency_offset,
    estimate_bpsk_frequency_offset,
    simulate_bpsk_frequency_offset,
)

client = TestClient(main.app)


@pytest.mark.parametrize("epsilon", [0.0, 0.02, -0.02, 0.012, -0.012])
def test_squared_bpsk_estimator_recovers_signed_offset(epsilon):
    signal = simulate_bpsk_frequency_offset(seed=1977, n_symbols=4096, eb_n0_db=8, epsilon=epsilon)
    estimate = estimate_bpsk_frequency_offset(signal["received"])
    assert math.isfinite(estimate)
    assert abs(estimate - epsilon) < 0.001


@pytest.mark.parametrize("epsilon", [0.02, -0.02])
def test_frequency_rotation_direction_and_compensation_restore_phase(epsilon):
    signal = simulate_bpsk_frequency_offset(seed=712, n_symbols=4096, eb_n0_db=12, epsilon=epsilon)
    rx = signal["received"]
    squared_correlation = np.sum(rx[1:] ** 2 * np.conjugate(rx[:-1] ** 2))
    assert np.sign(np.angle(squared_correlation)) == np.sign(epsilon)

    compensated = compensate_bpsk_frequency_offset(rx, epsilon)
    corrected = np.sum(compensated[1:] ** 2 * np.conjugate(compensated[:-1] ** 2))
    residual = np.angle(corrected) / (4 * np.pi)
    assert abs(residual) < 0.001
    # Compensation operates on the same received samples and does not regenerate noise.
    np.testing.assert_allclose(compensated, rx * np.exp(-1j * 2 * np.pi * epsilon * np.arange(rx.size)))


def test_zero_offset_coherent_ber_is_statistically_consistent_with_bpsk_theory():
    signal = simulate_bpsk_frequency_offset(seed=42, n_symbols=100_000, eb_n0_db=8, epsilon=0.0)
    theoretical = signal["ber_theoretical"]
    standard_deviation = math.sqrt(theoretical * (1 - theoretical) / signal["bits"].size)
    assert abs(signal["ber"] - theoretical) < 5 * standard_deviation + 1 / signal["bits"].size
    assert signal["ber"] == calculate_bpsk_ber(signal["bits"], signal["received"])["ber"]


@pytest.mark.parametrize("epsilon", [0.0, 0.02, -0.02])
def test_api_challenge_hides_state_and_completes_measure_diagnose_compensate_feedback(monkeypatch, epsilon):
    monkeypatch.setattr(main.secrets, "choice", lambda _: epsilon)
    monkeypatch.setattr(main.secrets, "randbits", lambda _: 42)
    challenge = client.post("/api/stage04/challenges")
    assert challenge.status_code == 200
    data = challenge.json()
    cid = data["challenge_id"]
    assert data["epsilon_unit"] == "cycles per symbol (Δf·Ts)"
    assert len(data["signal"]["i"]) == 512
    assert len(data["signal"]["q"]) == 512
    assert len(data["signal"]["constellation"]) == 512
    assert len(data["signal"]["phase_rad"]) == 64
    for hidden in ("epsilon", "actual_fault", "diagnosis", "estimate", "seed", "reference"):
        assert hidden not in data

    estimate = client.get(f"/api/stage04/challenges/{cid}/estimate")
    assert estimate.status_code == 200
    measured = estimate.json()["epsilon_hat"]
    assert abs(measured - epsilon) < 0.001
    assert "epsilon" not in estimate.json()

    wrong_choice = "no_offset" if epsilon else "frequency_offset"
    wrong = client.post("/api/stage04/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": wrong_choice})
    assert wrong.status_code == 200 and wrong.json()["correct"] is False
    assert "epsilon" not in wrong.json()
    right_choice = "frequency_offset" if epsilon else "no_offset"
    right = client.post("/api/stage04/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": right_choice})
    assert right.status_code == 200 and right.json()["correct"] is True

    compensated = client.post("/api/stage04/challenges/compensate", json={"challenge_id": cid, "epsilon_hat": measured})
    assert compensated.status_code == 200
    result = compensated.json()
    assert result["before"]["ber"] == result["before"]["n_errors"] / data["n_symbols"]
    assert result["after"]["ber"] == result["after"]["n_errors"] / data["n_symbols"]
    if epsilon:
        assert result["after"]["n_errors"] < result["before"]["n_errors"]

    feedback = client.get(f"/api/stage04/challenges/{cid}/feedback")
    assert feedback.status_code == 200
    report = feedback.json()
    assert report["actual_fault"]["epsilon"] == epsilon
    assert report["estimate"]["epsilon_hat"] == measured
    assert report["estimate"]["error"] == measured - epsilon
    assert report["ber"]["after"] == result["after"]


def test_frequency_challenge_flow_gates_and_rejects_invalid_parameters(monkeypatch):
    monkeypatch.setattr(main.secrets, "choice", lambda _: 0.02)
    monkeypatch.setattr(main.secrets, "randbits", lambda _: 42)
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/stage04/challenges/{missing}/estimate").status_code == 404
    challenge = client.post("/api/stage04/challenges").json()
    cid = challenge["challenge_id"]
    assert client.post("/api/stage04/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "frequency_offset"}).status_code == 409
    assert client.post("/api/stage04/challenges/compensate", json={"challenge_id": cid, "epsilon_hat": 0.02}).status_code == 409
    assert client.get(f"/api/stage04/challenges/{cid}/estimate").status_code == 200
    client.post("/api/stage04/challenges/diagnosis", json={"challenge_id": cid, "suspected_fault": "frequency_offset"})
    for invalid in (0.25, -0.25, "0.02", True, float("nan")):
        response = client.post("/api/stage04/challenges/compensate", json={"challenge_id": cid, "epsilon_hat": invalid})
        assert response.status_code == 422


@pytest.mark.parametrize("epsilon", [0.25, -0.25, float("inf"), float("nan")])
def test_simulator_rejects_out_of_range_or_nonfinite_frequency(epsilon):
    with pytest.raises(ValueError):
        simulate_bpsk_frequency_offset(seed=1, epsilon=epsilon)
