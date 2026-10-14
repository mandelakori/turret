"""Pixel error -> requested pulse-change rate -> incremental pulse correction.

This module has no camera, network, or GPIO imports. Units make the boundary
explicit: px * us/(s*px) = us/s, then us/s * s = us. The sign that makes error
shrink belongs to the axis configuration, not to the detector.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ControlSettings:
    gain_us_per_second_per_pixel: float = 1.0
    max_rate_us_per_second: float = 250.0
    max_dt_s: float = 0.1

    def __post_init__(self):
        values = (
            self.gain_us_per_second_per_pixel,
            self.max_rate_us_per_second,
            self.max_dt_s,
        )
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError("Control settings must be finite and positive")


@dataclass(frozen=True)
class Correction:
    pan_delta_us: float
    tilt_delta_us: float
    pan_rate_us_s: float
    tilt_rate_us_s: float
    dt_used_s: float


def effective_error(error_px, deadzone_px=15.0):
    """Continuous deadband: errors of +15, +16, -16 give 0, +1, -1 px.

    Subtracting the deadzone outside the central region avoids jumping from
    zero correction directly to a 15-pixel correction at its edge.
    """
    if not math.isfinite(error_px) or not math.isfinite(deadzone_px) or deadzone_px < 0:
        raise ValueError("Error must be finite and deadzone nonnegative")
    return math.copysign(max(abs(error_px) - deadzone_px, 0.0), error_px)


def calculate_correction(e_effective_x, e_effective_y, delta_t, settings=None):
    """Calculate signed pulse increments; do not touch an actuator here.

    delta_t is host elapsed time in seconds, NOT exposure time or frame age.
    Long pauses are capped: never catch up a stalled program with a huge move.
    The caller must separately reject old observations. Returning named fields
    deliberately replaces the old radian tuple so a units mismatch is visible.
    """
    settings = settings or ControlSettings()
    if (
        not all(math.isfinite(v) for v in (e_effective_x, e_effective_y, delta_t))
        or delta_t < 0
    ):
        raise ValueError("Errors/time must be finite; time cannot be negative")
    dt = min(delta_t, settings.max_dt_s)

    def rate(error):
        requested = settings.gain_us_per_second_per_pixel * error
        return max(
            -settings.max_rate_us_per_second,
            min(settings.max_rate_us_per_second, requested),
        )

    pan_rate, tilt_rate = rate(e_effective_x), rate(e_effective_y)
    return Correction(pan_rate * dt, tilt_rate * dt, pan_rate, tilt_rate, dt)
