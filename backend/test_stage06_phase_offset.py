import math
import numpy as np
import pytest
from fastapi.testclient import TestClient
from main import app, stage06_challenge_cache
from phase_offset import simulate_phase_offset, estimate_phase, compensate_phase, measure_ber

client=TestClient(app)

@pytest.mark.parametrize("phase",[math.radians(37),math.radians(-42)])
def test_estimator_sign_units_and_compensation(phase):
    exp=simulate_phase_offset(seed=71,phase_rad=phase,n_symbols=20000,eb_n0_db=18)
    estimate=estimate_phase(exp["received"])
    assert estimate*phase>0
    assert abs(estimate-phase)<math.radians(1)
    corrected=compensate_phase(exp["received"],estimate)
    assert abs(np.angle(np.mean(corrected**2)))<math.radians(2)
    assert measure_ber(exp["bits"],corrected)["n_errors"] <= exp["before"]["n_errors"]

def test_normal_control_is_zero_phase_and_measurement_is_noise_derived():
    x=simulate_phase_offset(seed=5,phase_rad=0)
    assert x["phase_rad"]==0
    assert abs(estimate_phase(x["received"])) < math.radians(5)

@pytest.mark.parametrize("scenario,expected_sign",[("normal",0),("phase_positive",1),("phase_negative",-1)])
def test_api_challenge_scenario_signal_direction_and_answer_protection(scenario,expected_sign):
    stage06_challenge_cache.clear()
    response=client.post("/api/stage06/challenges",json={"scenario":scenario})
    assert response.status_code==200
    data=response.json()
    assert not ({"phase_rad","phase_deg","actual_fault","reference_ber"}&data.keys())
    hidden=stage06_challenge_cache[data["challenge_id"]]
    assert (hidden["phase_rad"]>0)-(hidden["phase_rad"]<0)==expected_sign
    observed=client.get(f"/api/stage06/challenges/{data['challenge_id']}/measurement").json()["phase_hat_deg"]
    if expected_sign: assert observed*expected_sign>0

def test_api_protects_answer_retry_and_compensation_input():
    stage06_challenge_cache.clear()
    created=client.post("/api/stage06/challenges",json={"scenario":"phase"})
    assert created.status_code==200
    data=created.json(); assert "phase_rad" not in data and "phase_deg" not in data and "actual_fault" not in data
    cid=data["challenge_id"]
    measurement=client.get(f"/api/stage06/challenges/{cid}/measurement").json()
    assert -90<=measurement["phase_hat_deg"]<90
    wrong=client.post("/api/stage06/challenges/diagnosis",json={"challenge_id":cid,"suspected_fault":"none"})
    assert wrong.status_code==200 and not wrong.json()["correct"]
    right=client.post("/api/stage06/challenges/diagnosis",json={"challenge_id":cid,"suspected_fault":"phase_offset"})
    assert right.json()["correct"]
    assert client.post("/api/stage06/challenges/compensate",json={"challenge_id":cid,"compensation_deg":float("nan")}).status_code==422
    assert client.post("/api/stage06/challenges/compensate",json={"challenge_id":cid,"compensation_deg":measurement["phase_hat_deg"]}).status_code==200
    review=client.get(f"/api/stage06/challenges/{cid}/feedback")
    assert review.status_code==200 and "phase_deg" in review.json()["actual_fault"]

def test_phase_rotation_and_bad_estimate_are_respected():
    samples=np.array([1+0j,-1+0j])*np.exp(1j*math.radians(30))
    out=compensate_phase(samples,math.radians(30))
    assert np.allclose(out,[1,-1])
    assert not np.allclose(compensate_phase(samples,math.radians(-30)),out)
    with pytest.raises(ValueError): compensate_phase(samples,float("inf"))
