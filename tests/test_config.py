from pathlib import Path
import re
import unittest
from config import PROJECT_ROOT, load_config


class ConfigTests(unittest.TestCase):
    def test_firmware_settings_match_python(self):
        cfg = load_config()
        source = (
            PROJECT_ROOT
            / "firmware/turret_controller/TurretController/TurretController.ino"
        ).read_text()
        for field, key in [
            ("MIN_US", "minimum_us"),
            ("MAX_US", "maximum_us"),
            ("ZERO_US", "reference_us"),
        ]:
            values = [
                int(v)
                for v in re.search(rf"{field}\[2\] = \{{([^}}]+)\}}", source)
                .group(1)
                .split(",")
            ]
            self.assertEqual(values, [cfg["tilt"][key], cfg["pan"][key]])
        for field, key in [
            ("STEP_US", "step_us"),
            ("STEP_INTERVAL_MS", "interval_ms"),
            ("MANAGED_TIMEOUT_MS", "managed_timeout_ms"),
        ]:
            value = int(re.search(rf"{field} = (\d+)", source).group(1))
            self.assertEqual(value, cfg["firmware"][key])

    def test_no_import_time_camera_or_model_load(self):
        import tracking.targetting
        import vision.tracking
        import control.mouse_panel

        self.assertIsNone(vision.tracking._default_detector)
