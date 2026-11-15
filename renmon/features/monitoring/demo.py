"""Synthetic readings using the profile's decoded state domain."""

import math


def demo_value(signal, t):
    # State codes are discrete profile interpretations, never sine-wave readings.
    if signal.kind == "state":
        choices = signal.demo_states
        return choices[int(t / 6) % len(choices)] if choices else None
    seed = sum(ord(c) for c in signal.code)
    baselines = {
        "PR064": (85, 5),
        "PR383": (12, 3),
        "PR071": (13.8, 0.3),
        "PR059": (25, 4),
        "PR038": (350, 35),
    }
    base, amplitude = baselines.get(signal.code, (15 + seed % 50, 2 + seed % 5))
    return round(base + amplitude * math.sin(t / (3 + seed % 5)), 3)
