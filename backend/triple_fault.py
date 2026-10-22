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
MIN_SYMBOLS = 128
MAX_SYMBOLS = 1_000_000  # Match the existing simulation API limit.
MIN_EB_N0_DB = -10.0
MAX_EB_N0_DB = 30.0


def _finite_real(name: str, value) -> float:
    """Return a supported real scalar as float, with a stable ValueError contract."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite real number") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _signal_array(received, *, minimum_size: int, operation: str) -> np.ndarray:
    values = np.asarray(received)
    if values.ndim != 1 or values.size < minimum_size or values.dtype.kind not in "fc":
        raise ValueError(f"received must be a one-dimensional floating-point or complex signal with at least {minimum_size} samples")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("received must contain only finite samples")
    if operation == "estimate":
        # The squared-BPSK estimator squares each sample and sums an FFT. Keep
        # that intermediate comfortably inside binary64's finite range.
        safe_magnitude = math.sqrt(np.finfo(np.float64).max / (16.0 * values.size))
        # Component-wise bounds avoid overflow inside abs(complex) itself.
        if np.any(np.abs(values.real) > safe_magnitude) or np.any(np.abs(values.imag) > safe_magnitude):
            raise ValueError("received magnitude exceeds the finite range supported by Stage07 estimation")
    return values

def simulate_triple_fault(*,seed:int,scenario:str,n_symbols:int=4096,eb_n0_db:float=8.0)->dict:
    if scenario not in SCENARIOS: raise ValueError("unknown Stage07 scenario")
    if isinstance(seed,bool) or not isinstance(seed,int) or seed<0: raise ValueError("seed must be non-negative integer")
    if isinstance(n_symbols, bool) or not isinstance(n_symbols, int) or not MIN_SYMBOLS <= n_symbols <= MAX_SYMBOLS:
        raise ValueError(f"n_symbols must be an integer between {MIN_SYMBOLS} and {MAX_SYMBOLS}")
    eb_n0 = _finite_real("eb_n0_db", eb_n0_db)
    if not MIN_EB_N0_DB <= eb_n0 <= MAX_EB_N0_DB:
        raise ValueError(f"eb_n0_db must be between {MIN_EB_N0_DB:g} and {MAX_EB_N0_DB:g} dB")
    dc_on,eps_on,phi_on=SCENARIOS[scenario]
    rng=np.random.default_rng(seed); bits=rng.integers(0,2,n_symbols,dtype=np.int8); symbols=(2*bits-1).astype(float); n=np.arange(n_symbols)
    dc=float(rng.choice(DC_VALUES)) if dc_on else 0.; epsilon=float(rng.choice(EPS_VALUES)) if eps_on else 0.; phi=float(rng.choice(PHI_VALUES)) if phi_on else 0.
    sigma=math.sqrt(.5*10**(-eb_n0/10)); noise=sigma*(rng.standard_normal(n_symbols)+1j*rng.standard_normal(n_symbols))
    received=symbols*np.exp(1j*(2*np.pi*epsilon*n+phi))+dc+noise
    if not np.all(np.isfinite(noise)) or not np.all(np.isfinite(received)) or not math.isfinite(sigma):
        raise ValueError("Stage07 simulation produced non-finite samples")
    return {"bits":bits,"symbols":symbols,"noise":noise,"received":received,"scenario":scenario,"dc":dc,"epsilon":epsilon,"phi":phi,"n":n,"sigma":sigma,"before":calculate_bpsk_ber(bits,received),"n_symbols":n_symbols,"eb_n0_db":eb_n0_db}

def estimate_triple(received:np.ndarray)->dict:
    z=_signal_array(received,minimum_size=2,operation="estimate")
    dc=estimate_dc_offset(z)
    centered=z-dc
    if not np.all(np.isfinite(centered.real)) or not np.all(np.isfinite(centered.imag)):
        raise ValueError("DC-centered signal must contain only finite samples")
    eps=estimate_bpsk_frequency_offset(centered)
    derotated=compensate_bpsk_frequency_offset(centered,eps)
    if not np.all(np.isfinite(derotated.real)) or not np.all(np.isfinite(derotated.imag)):
        raise ValueError("frequency-corrected signal must contain only finite samples")
    phi=estimate_phase(derotated)
    if not all(math.isfinite(value) for value in (dc, eps, phi)):
        raise ValueError("Stage07 estimates must be finite")
    return {"dc_hat":dc,"epsilon_hat":eps,"phi_hat_rad":phi,"phi_hat_deg":math.degrees(phi)}

def compensate_triple(received,dc_hat,epsilon_hat,phi_hat_rad,mode):
    if mode not in ("dc","frequency","phase","joint"): raise ValueError("invalid compensation mode")
    z=_signal_array(received,minimum_size=1,operation="compensate")
    dc_value=_finite_real("dc_hat",dc_hat)
    epsilon_value=_finite_real("epsilon_hat",epsilon_hat)
    phase_value=_finite_real("phi_hat_rad",phi_hat_rad)
    if abs(dc_value) > 2.0: raise ValueError("abs(dc_hat) must be at most 2")
    if abs(epsilon_value) >= MAX_UNAMBIGUOUS_OFFSET: raise ValueError("abs(epsilon_hat) must be less than 0.25 cycles per symbol")
    if abs(phase_value) > math.pi: raise ValueError("phi_hat_rad must be within ±pi radians")
    if mode in ("dc","joint"): z=z-dc_value
    if mode in ("frequency","joint"): z=compensate_bpsk_frequency_offset(z,epsilon_value)
    if mode in ("phase","joint"): z=z*np.exp(-1j*phase_value)
    if not np.all(np.isfinite(z.real)) or not np.all(np.isfinite(z.imag)):
        raise ValueError("compensation produced non-finite samples")
    return z
