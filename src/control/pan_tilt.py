"""Maintain bounded floating-point pulse targets, not measured shaft angles."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AxisLimits:
    minimum_us: int
    maximum_us: int
    reference_us: int

    def __post_init__(self):
        if not 0 < self.minimum_us <= self.reference_us <= self.maximum_us < 20000:
            raise ValueError("Reference must lie inside a positive pulse interval")

    def clamp(self, pulse):
        if not math.isfinite(pulse):
            raise ValueError("Pulse must be finite")
        return max(self.minimum_us, min(self.maximum_us, pulse))


class PulseTargets:
    """Integrate corrections once per new observation.

    Keep fractional microseconds internally so sub-microsecond increments can
    accumulate. Saturate the stored state as well as the outgoing command;
    otherwise it can drift past a limit and take many frames to recover.
    This object represents host targets, not ESP32 ramp state or actual angle.
    """

    def __init__(self, pan, tilt):
        self.pan_limits, self.tilt_limits = pan, tilt
        self.pan_us = float(pan.reference_us)
        self.tilt_us = float(tilt.reference_us)

    def advance(self, correction, pan_sign=1, tilt_sign=0):
        if pan_sign not in (-1, 0, 1) or tilt_sign not in (-1, 0, 1):
            raise ValueError("Axis sign must be -1, 0 (disabled), or +1")
        self.pan_us = self.pan_limits.clamp(
            self.pan_us + pan_sign * correction.pan_delta_us
        )
        self.tilt_us = self.tilt_limits.clamp(
            self.tilt_us + tilt_sign * correction.tilt_delta_us
        )
        return self.command()

    def command(self):
        """Round only at the actuator boundary; integers are pulse requests."""
        return round(self.pan_us), round(self.tilt_us)

    def reset(self):
        self.pan_us = float(self.pan_limits.reference_us)
        self.tilt_us = float(self.tilt_limits.reference_us)


def cursor_to_pulses(x, y, width, height, pan, tilt):
    """Absolute mouse position -> bounded pulse targets for a manual bench UI.

    This is a control-panel mapping, not visual servoing or degrees calibration.
    Left sends pan maximum, right sends pan minimum (observed direction).
    Top sends tilt minimum; that is a UI choice until tilt direction is checked.
    """
    if width <= 1 or height <= 1 or not all(math.isfinite(v) for v in (x, y)):
        raise ValueError("Invalid cursor coordinates or panel dimensions")
    fx, fy = max(0.0, min(1.0, x / (width - 1))), max(0.0, min(1.0, y / (height - 1)))
    return (
        round(pan.maximum_us - fx * (pan.maximum_us - pan.minimum_us)),
        round(tilt.minimum_us + fy * (tilt.maximum_us - tilt.minimum_us)),
    )
