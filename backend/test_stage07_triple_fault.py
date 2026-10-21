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
