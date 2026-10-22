import math
import numpy as np
import pytest
from fastapi.testclient import TestClient
from main import app, stage07_challenge_cache
from triple_fault import SCENARIOS, simulate_triple_fault, estimate_triple, compensate_triple
from frequency_offset import calculate_bpsk_ber

client=TestClient(app)

@pytest.mark.parametrize("scenario",list(SCENARIOS))
def test_all_eight_scenarios_are_deterministic_and_match_fault_mask(scenario):
    a=simulate_triple_fault(seed=348,scenario=scenario,n_symbols=1200)
    b=simulate_triple_fault(seed=348,scenario=scenario,n_symbols=1200)
    assert SCENARIOS[scenario]==(a['dc']!=0,a['epsilon']!=0,a['phi']!=0)
    assert np.array_equal(a['bits'],b['bits']) and np.array_equal(a['noise'],b['noise'])
    assert np.array_equal(a['received'],b['received'])
    assert a['received'].shape==(1200,)

@pytest.mark.parametrize("scenario",["frequency","dc_frequency","frequency_phase","triple"])
def test_frequency_estimator_sign_and_magnitude_under_dc_phase(scenario):
    x=simulate_triple_fault(seed=129,scenario=scenario,n_symbols=20000,eb_n0_db=18)
    m=estimate_triple(x['received'])
    assert m['epsilon_hat']*x['epsilon']>0
    assert abs(m['epsilon_hat']-x['epsilon'])<0.001

def test_phase_estimation_mod_pi_and_sequential_error_propagation():
    x=simulate_triple_fault(seed=129,scenario='triple',n_symbols=20000,eb_n0_db=18)
    m=estimate_triple(x['received'])
    assert -math.pi/2<=m['phi_hat_rad']<math.pi/2
    assert abs(m['phi_hat_rad']-x['phi'])<math.radians(2)
    assert abs(m['dc_hat']-x['dc'])<.05

@pytest.mark.parametrize("mode",["dc","frequency","phase","joint"])
def test_compensation_uses_same_observations_and_correct_direction(mode):
    x=simulate_triple_fault(seed=129,scenario='triple',n_symbols=12000,eb_n0_db=18); m=estimate_triple(x['received'])
    out=compensate_triple(x['received'],m['dc_hat'],m['epsilon_hat'],m['phi_hat_rad'],mode)
    assert out.shape==x['received'].shape
    assert np.array_equal(x['noise'],simulate_triple_fault(seed=129,scenario='triple',n_symbols=12000,eb_n0_db=18)['noise'])
    if mode=='joint': assert calculate_bpsk_ber(x['bits'],out)['ber']<calculate_bpsk_ber(x['bits'],x['received'])['ber']
    wrong=compensate_triple(x['received'],0.,0.,0.,mode)
    if mode!='dc' or x['dc']!=0: assert not np.allclose(out,wrong)

def test_api_hides_answers_and_allows_retry_then_four_compensations():
    stage07_challenge_cache.clear()
    created=client.post('/api/stage07/challenges')
    assert created.status_code==200
    body=created.json()
    assert not {'scenario','dc','epsilon','phi','actual_fault','ber_theoretical','reference_ber'}&body.keys()
    cid=body['challenge_id']
    assert client.get(f'/api/stage07/challenges/{cid}/measurement').status_code==200
    actual=stage07_challenge_cache[cid]['scenario']
    wrong=next(s for s in SCENARIOS if s!=actual)
    assert client.post('/api/stage07/challenges/diagnosis',json={'challenge_id':cid,'suspected_fault':wrong}).json()['correct'] is False
    assert client.post('/api/stage07/challenges/diagnosis',json={'challenge_id':cid,'suspected_fault':actual}).json()['correct'] is True
    m=stage07_challenge_cache[cid]['measurement']; payload={'challenge_id':cid,'dc_hat':m['dc_hat'],'epsilon_hat':m['epsilon_hat'],'phi_hat_deg':m['phi_hat_deg']}
    for mode in ('dc','frequency','phase','joint'):
        assert client.post('/api/stage07/challenges/compensate',json={**payload,'mode':mode}).status_code==200
    review=client.get(f'/api/stage07/challenges/{cid}/feedback')
    assert review.status_code==200 and len(review.json()['compensation'])==4
    assert client.post('/api/stage07/challenges/compensate',json={**payload,'mode':'joint','dc_hat':float('inf')}).status_code==422

def test_normal_challenge_is_permitted_and_diagnosis_is_not_forced_to_correct_fault():
    x=simulate_triple_fault(seed=7,scenario='none',n_symbols=256)
    assert x['dc']==x['epsilon']==x['phi']==0
    assert estimate_triple(x['received'])['epsilon_hat']==0


@pytest.mark.parametrize("n_symbols", [128, 4096, 1_000_000])
def test_simulator_accepts_documented_symbol_count_boundaries(n_symbols):
    result = simulate_triple_fault(seed=1, scenario="none", n_symbols=n_symbols)
    assert result["received"].shape == (n_symbols,)
    assert result["bits"].shape == (n_symbols,)
    assert result["before"]["ber"] == result["before"]["n_errors"] / n_symbols
    assert np.isfinite(result["received"]).all()


@pytest.mark.parametrize("n_symbols", [0, -1, 127, 1.5, True, float("nan"), float("inf"), 1_000_001])
def test_simulator_rejects_invalid_symbol_counts_with_value_error(n_symbols):
    with pytest.raises(ValueError, match="n_symbols must be an integer between"):
        simulate_triple_fault(seed=1, scenario="none", n_symbols=n_symbols)


@pytest.mark.parametrize("eb_n0_db", [-10, 8, 30])
def test_simulator_accepts_supported_eb_n0_values(eb_n0_db):
    result = simulate_triple_fault(seed=1, scenario="none", n_symbols=128, eb_n0_db=eb_n0_db)
    assert math.isfinite(result["sigma"])
    assert np.isfinite(result["received"]).all()


@pytest.mark.parametrize("eb_n0_db", [float("nan"), float("inf"), -float("inf"), -10000.0, 10000.0, 30.0001, -10.0001])
def test_simulator_rejects_unsupported_eb_n0_with_value_error(eb_n0_db):
    with pytest.raises(ValueError, match="eb_n0_db"):
        simulate_triple_fault(seed=1, scenario="none", n_symbols=128, eb_n0_db=eb_n0_db)


@pytest.mark.parametrize("estimate", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("parameter", ["dc", "phase"])
def test_compensation_rejects_nonfinite_dc_and_phase_before_math(parameter, estimate):
    values = {"dc": 0.0, "phase": 0.0}
    values[parameter] = estimate
    with pytest.raises(ValueError, match=f"{parameter}_hat|phi_hat_rad"):
        compensate_triple(np.array([1 + 0j]), values["dc"], 0.0, values["phase"], "joint")


@pytest.mark.parametrize("received", [
    np.ones((2, 2), dtype=np.complex128),
    np.ones(1, dtype=np.complex128),
    np.array([1.0, 2.0], dtype=object),
    np.array([1.0, 2.0], dtype=np.int64),
    np.array([1 + 0j, complex(float("nan"), 0)], dtype=np.complex128),
    np.array([1 + 0j, complex(0, float("inf"))], dtype=np.complex128),
    np.array([complex(1e200, 0), complex(1e200, 0)], dtype=np.complex128),
])
def test_estimator_rejects_invalid_signal_shape_type_and_values(received):
    with pytest.raises(ValueError, match="received must|received magnitude"):
        estimate_triple(received)


@pytest.mark.parametrize("received", [
    np.ones((2, 2), dtype=np.complex128),
    np.array([], dtype=np.complex128),
    np.array([1.0], dtype=object),
    np.array([1.0], dtype=np.int64),
    np.array([complex(float("inf"), 0)], dtype=np.complex128),
    np.array([complex(0, float("nan"))], dtype=np.complex128),
])
def test_compensator_rejects_invalid_signal_shape_type_and_values(received):
    with pytest.raises(ValueError, match="received must"):
        compensate_triple(received, 0.0, 0.0, 0.0, "joint")


@pytest.mark.parametrize("parameter,value", [
    ("dc_hat", True), ("dc_hat", 2.01), ("epsilon_hat", float("nan")),
    ("epsilon_hat", 0.25), ("phi_hat_rad", float("inf")), ("phi_hat_rad", math.pi + 0.01),
])
def test_compensator_rejects_invalid_scalar_contract(parameter, value):
    args = {"dc_hat": 0.0, "epsilon_hat": 0.0, "phi_hat_rad": 0.0}
    args[parameter] = value
    with pytest.raises(ValueError, match=parameter):
        compensate_triple(np.array([1 + 0j]), args["dc_hat"], args["epsilon_hat"], args["phi_hat_rad"], "joint")


def test_normal_joint_path_matches_prevalidation_baseline_and_preserves_ber_denominator():
    x = simulate_triple_fault(seed=129, scenario="triple", n_symbols=4096, eb_n0_db=18)
    m = estimate_triple(x["received"])
    out = compensate_triple(x["received"], m["dc_hat"], m["epsilon_hat"], m["phi_hat_rad"], "joint")
    # Captured before the validation-only change from the same baseline checkout.
    np.testing.assert_allclose(x["received"][:3], [
        -1.1245335451826017-0.7292062241922592j,
        -0.9080778323168244-0.7501853862534914j,
        -0.7326767377817409-0.8193168412592978j,
    ], rtol=0, atol=0)
    assert x["before"] == {"n_errors": 2023, "ber": 2023 / 4096}
    assert m == {
        "dc_hat": -0.3569019509164924,
        "epsilon_hat": 0.01999664306640625,
        "phi_hat_rad": 0.8302114230961948,
        "phi_hat_deg": 47.567610646961874,
    }
    assert out.shape == x["received"].shape == (4096,)
    assert np.isfinite(out).all()
    assert calculate_bpsk_ber(x["bits"], out) == {"n_errors": 0, "ber": 0.0}
    assert calculate_bpsk_ber(x["bits"], out)["ber"] == calculate_bpsk_ber(x["bits"], out)["n_errors"] / len(x["bits"])
