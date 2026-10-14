"""Print controller calculations for synthetic pixel errors; no mechanical simulation."""

from config import load_config
from control.controller import ControlSettings, effective_error, calculate_correction
from control.pan_tilt import AxisLimits, PulseTargets


def main(argv=None):
    cfg = load_config()
    c = cfg["control"]
    settings = ControlSettings(
        c["gain_us_per_second_per_pixel"], c["max_rate_us_per_second"], c["max_dt_s"]
    )
    state = PulseTargets(AxisLimits(**cfg["pan"]), AxisLimits(**cfg["tilt"]))
    print("Synthetic errors. dt=0.02 s. No hardware or model loaded.")
    for raw in [-100, -50, -16, -15, 0, 15, 16, 50, 100]:
        error = effective_error(raw, c["deadzone_px"])
        correction = calculate_correction(error, 0, 0.02, settings)
        pan, _ = state.advance(correction, pan_sign=1, tilt_sign=0)
        print(
            f"error={raw:4d}px effective={error:6.1f}px delta={correction.pan_delta_us:7.3f}us target={state.pan_us:8.3f}us sent={pan}"
        )


if __name__ == "__main__":
    main()
