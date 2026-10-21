"""Stage07 unified BPSK model with DC, carrier frequency and phase faults."""
from __future__ import annotations
import math
import numpy as np
from frequency_offset import MAX_UNAMBIGUOUS_OFFSET, estimate_bpsk_frequency_offset, compensate_bpsk_frequency_offset, calculate_bpsk_ber
from multi_fault import estimate_dc_offset
from phase_offset import estimate_phase

SCENARIOS = {
    "none": (False, False, False), "dc": (True, False, False),
    "frequency": (False, True, False), "phase": (False, False, True),
    "dc_frequency": (True, True, False), "dc_phase": (True, False, True),
    "frequency_phase": (False, True, True), "triple": (True, True, True),
}
DC_VALUES=(-0.35,0.35); EPS_VALUES=(-0.02,0.02); PHI_VALUES=(-math.pi/4,math.pi/4)

def simulate_triple_fault(*,seed:int,scenario:str,n_symbols:int=4096,eb_n0_db:float=8.0)->dict:
    if scenario not in SCENARIOS: raise ValueError("unknown Stage07 scenario")
    if isinstance(seed,bool) or not isinstance(seed,int) or seed<0: raise ValueError("seed must be non-negative integer")
    dc_on,eps_on,phi_on=SCENARIOS[scenario]
    rng=np.random.default_rng(seed); bits=rng.integers(0,2,n_symbols,dtype=np.int8); symbols=(2*bits-1).astype(float); n=np.arange(n_symbols)
    dc=float(rng.choice(DC_VALUES)) if dc_on else 0.; epsilon=float(rng.choice(EPS_VALUES)) if eps_on else 0.; phi=float(rng.choice(PHI_VALUES)) if phi_on else 0.
    sigma=math.sqrt(.5*10**(-eb_n0_db/10)); noise=sigma*(rng.standard_normal(n_symbols)+1j*rng.standard_normal(n_symbols))
    received=symbols*np.exp(1j*(2*np.pi*epsilon*n+phi))+dc+noise
    return {"bits":bits,"symbols":symbols,"noise":noise,"received":received,"scenario":scenario,"dc":dc,"epsilon":epsilon,"phi":phi,"n":n,"sigma":sigma,"before":calculate_bpsk_ber(bits,received),"n_symbols":n_symbols,"eb_n0_db":eb_n0_db}

def estimate_triple(received:np.ndarray)->dict:
    z=np.asarray(received)
    dc=estimate_dc_offset(z)
    centered=z-dc
    eps=estimate_bpsk_frequency_offset(centered)
    derotated=compensate_bpsk_frequency_offset(centered,eps)
    phi=estimate_phase(derotated)
    return {"dc_hat":dc,"epsilon_hat":eps,"phi_hat_rad":phi,"phi_hat_deg":math.degrees(phi)}

def compensate_triple(received,dc_hat,epsilon_hat,phi_hat_rad,mode):
    z=np.asarray(received); n=np.arange(z.size)
    if mode not in ("dc","frequency","phase","joint"): raise ValueError("invalid compensation mode")
    if mode in ("dc","joint"): z=z-dc_hat
    if mode in ("frequency","joint"): z=compensate_bpsk_frequency_offset(z,epsilon_hat)
    if mode in ("phase","joint"): z=z*np.exp(-1j*phi_hat_rad)
    return z
