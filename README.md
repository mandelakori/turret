# turret

ESP32 pan/tilt control through a PCA9685, with a Python mouse panel and a camera detection preview.

The mouse panel can drive the servos over USB. The camera preview draws detections and calculates pulse targets, but does not send them to hardware. Network control and closed-loop camera tracking are unfinished.

## Setup

Use Python 3.11 or newer. From the repository root:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/run.py simulate
python tools/run.py mouse
```

`simulate` prints controller calculations without hardware or dependencies. `mouse` starts in dry-run mode.

For camera preview, provide compatible local Ultralytics weights:

```sh
python tools/run.py preview --source 0 --model /path/to/model.pt --log data/preview-001.csv
```

`--source` accepts a webcam index or stream URL. Model weights are not included. Each run needs a new log filename; existing logs are never overwritten. Press `q` to quit or `r` to reset the virtual targets.

## Firmware

There are two separate sketches. Upload only one:

| Sketch | Use |
| --- | --- |
| `firmware/turret_controller/TurretController/TurretController.ino` | Python mouse panel; managed `m PAN TILT` commands with a 500 ms timeout |
| `firmware/turret_manual_control/turret_manual_control/turret_manual_control.ino` | Standalone Serial Monitor control; adjustable speed with `s RATE` and `c PAN TILT [RATE]` |

Both use the ESP32 Arduino core and Adafruit PWM Servo Driver library. Open the sketch in its matching folder, select your board and port, and use **115200 baud / Newline**. SDA is GPIO 21, SCL is GPIO 22, and PWM frequency is 50 Hz.

For the Python panel, upload `TurretController.ino`, close Serial Monitor, then run:

```sh
python tools/run.py mouse --port COM5
```

Replace `COM5` with your device. Hold the left mouse button to move; release to hold. Tilt stays at its reference unless `--tilt` is supplied. The standalone manual sketch uses a different protocol and is not compatible with this panel.

Both sketches start by commanding their reference pulses directly. `x` stops stepping but keeps servo torque. Pulse limits are specific to the mechanism and need checking after any mounting or wiring change.

## Layout

- `src/control/`: pulse limits, controller calculations and mouse panel
- `src/vision/`: frame capture and detection
- `src/tracking/`: observation selection and preview loop
- `src/networking/`: USB serial protocol
- `configs/bench.json`: Python settings
- `firmware/`: the two ESP32 sketches
- `tests/`: Python tests and managed-controller host tests

The ESP32-CAM snapshot is incomplete and is not included. The preview can use a webcam or an existing stream. CAD, print files, personal notes, recordings and model weights are kept outside this repository.

## Checks

```sh
python tools/check.py
python tools/check_firmware.py
python firmware/turret_manual_control/turret_manual_control/tests/check.py
```

Python tests need NumPy. Firmware host checks need `g++`; they test logic against stubs, not the ESP32 toolchain or physical hardware.

## Updating

Edit Python settings in `configs/bench.json`. The managed firmware keeps its own constants; `test_config.py` checks that pulse limits and timing match. The standalone manual sketch is configured separately near the top of its source.

Work from this checkout and run the checks before committing. Stage the files you changed, inspect `git diff --cached`, then commit and push. Keep credentials, logs, weights and CAD out of commits; `.gitignore` covers those paths and file types.
