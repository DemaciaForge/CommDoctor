"""Stage06 constant carrier phase BPSK experiment primitives."""
from __future__ import annotations
import math
import numpy as np

def simulate_phase_offset(*, seed: int, phase_rad: float, n_symbols: int = 4096, eb_n0_db: float = 8.0) -> dict:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0: raise ValueError("seed must be a non-negative integer")
    if not isinstance(phase_rad, (int, float)) or isinstance(phase_rad, bool) or not math.isfinite(phase_rad) or abs(phase_rad) > math.pi/3: raise ValueError("phase_rad must be finite and within ±60 degrees")
    if not isinstance(n_symbols, int) or isinstance(n_symbols, bool) or n_symbols < 128: raise ValueError("n_symbols must be at least 128")
    if not isinstance(eb_n0_db, (int,float)) or isinstance(eb_n0_db,bool) or not math.isfinite(eb_n0_db): raise ValueError("eb_n0_db must be finite")
    rng=np.random.default_rng(seed); bits=rng.integers(0,2,n_symbols,dtype=np.int8); symbols=(2*bits-1).astype(float)
    sigma=math.sqrt(.5*10**(-eb_n0_db/10)); noise=sigma*(rng.standard_normal(n_symbols)+1j*rng.standard_normal(n_symbols))
    received=symbols*np.exp(1j*phase_rad)+noise
    return {"bits":bits,"symbols":symbols,"noise":noise,"received":received,"phase_rad":float(phase_rad),"sigma_iq":sigma,"n_symbols":n_symbols,"eb_n0_db":float(eb_n0_db),"before":measure_ber(bits,received)}

def measure_ber(bits, samples):
    decisions=(np.asarray(samples).real > 0).astype(np.int8); errors=int(np.count_nonzero(decisions != bits))
    return {"n_errors":errors,"ber":errors/len(bits)}

def estimate_phase(received: np.ndarray) -> float:
    z=np.asarray(received)
    if z.ndim!=1 or z.size<2 or z.dtype.kind not in "fc" or not np.all(np.isfinite(z.real)) or not np.all(np.isfinite(z.imag)): raise ValueError("received must be a finite one-dimensional complex signal")
    moment=np.sum(z*z)
    if not np.isfinite(moment) or abs(moment) <= np.finfo(float).tiny: raise ValueError("phase cannot be estimated from this signal")
    # BPSK squaring leaves phase modulo pi. Return the principal interval [-pi/2, pi/2).
    return float(((.5*np.angle(moment)+math.pi/2)%math.pi)-math.pi/2)

def compensate_phase(received: np.ndarray, compensation_rad: float) -> np.ndarray:
    z=np.asarray(received)
    if z.ndim!=1 or z.size==0 or z.dtype.kind not in "fc" or not np.all(np.isfinite(z.real)) or not np.all(np.isfinite(z.imag)): raise ValueError("received must be a finite one-dimensional complex signal")
    if isinstance(compensation_rad,bool) or not isinstance(compensation_rad,(int,float)) or not math.isfinite(compensation_rad) or abs(compensation_rad)>math.pi: raise ValueError("compensation angle must be finite and within ±180 degrees")
    return z*np.exp(-1j*float(compensation_rad))
