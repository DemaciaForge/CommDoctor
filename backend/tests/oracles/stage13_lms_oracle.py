"""Independent scalar LMS reference used by Stage13 contract tests."""
from __future__ import annotations

import math


def run(samples: tuple[float, ...], targets: tuple[float, ...], mu: float, taps: int = 5) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if len(samples) != len(targets) * taps:
        raise ValueError("flattened samples must contain one window per target")
    if not math.isfinite(mu) or mu <= 0:
        raise ValueError("mu must be positive and finite")
    weights = [0.0] * taps
    errors = []
    for row, desired in enumerate(targets):
        window = samples[row * taps:(row + 1) * taps]
        output = sum(weight * value for weight, value in zip(weights, window))
        error = desired - output
        errors.append(error * error)
        weights = [weight + mu * error * value for weight, value in zip(weights, window)]
    return tuple(weights), tuple(errors)
