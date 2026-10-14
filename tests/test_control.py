import math
import unittest
from config import load_config
from control.controller import (
    ControlSettings,
    calculate_correction,
    effective_error,
    Correction,
)
from control.pan_tilt import AxisLimits, PulseTargets, cursor_to_pulses


class ControlTests(unittest.TestCase):
    def setUp(self):
        cfg = load_config()
        self.pan = AxisLimits(**cfg["pan"])
        self.tilt = AxisLimits(**cfg["tilt"])

    def test_deadzone_is_continuous_and_signed(self):
        for raw, expected in [(0, 0), (15, 0), (-15, 0), (16, 1), (-16, -1), (100, 85)]:
            self.assertEqual(effective_error(raw), expected)

    def test_invalid_numeric_inputs_fail(self):
        for value in [math.nan, math.inf, -math.inf]:
            with self.assertRaises(ValueError):
                effective_error(value)
            with self.assertRaises(ValueError):
                calculate_correction(value, 0, 0.02)
        with self.assertRaises(ValueError):
            calculate_correction(1, 1, -1)
        with self.assertRaises(ValueError):
            ControlSettings(max_dt_s=0)

    def test_units_and_rate_limit(self):
        result = calculate_correction(100, -1000, 0.02)
        self.assertEqual(result.pan_delta_us, 2)
        self.assertEqual(result.tilt_delta_us, -5)
        self.assertEqual(result.tilt_rate_us_s, -250)

    def test_long_gap_does_not_catch_up(self):
        result = calculate_correction(100, 0, 5)
        self.assertEqual(result.dt_used_s, 0.1)
        self.assertEqual(result.pan_delta_us, 10)

    def test_frame_rate_invariance_below_cap(self):
        one = sum(calculate_correction(50, 0, 0.02).pan_delta_us for _ in range(50))
        two = sum(calculate_correction(50, 0, 0.05).pan_delta_us for _ in range(20))
        self.assertAlmostEqual(one, two)

    def test_fractional_accumulation(self):
        state = PulseTargets(self.pan, self.tilt)
        for _ in range(10):
            state.advance(Correction(0.1, 5, 0, 0, 0.02), tilt_sign=0)
        self.assertEqual(state.command(), (1271, 1370))

    def test_mirror_sign_example(self):
        state = PulseTargets(self.pan, self.tilt)
        state.advance(calculate_correction(-85, 0, 0.02), pan_sign=1)
        self.assertLess(state.pan_us, 1270)  # physical right for mirrored image-left

    def test_saturation_has_no_hidden_out_of_range_accumulation(self):
        state = PulseTargets(self.pan, self.tilt)
        state.advance(Correction(10000, 0, 0, 0, 0.1))
        self.assertEqual(state.pan_us, 2850)
        state.advance(Correction(-1, 0, 0, 0, 0.1))
        self.assertEqual(state.pan_us, 2849)

    def test_mouse_is_absolute_not_error_integration(self):
        self.assertEqual(
            cursor_to_pulses(0, 0, 640, 480, self.pan, self.tilt), (2850, 400)
        )
        self.assertEqual(
            cursor_to_pulses(639, 479, 640, 480, self.pan, self.tilt), (420, 1510)
        )
        self.assertEqual(
            cursor_to_pulses(-200, 900, 640, 480, self.pan, self.tilt), (2850, 1510)
        )
