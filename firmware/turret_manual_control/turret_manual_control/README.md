# Manual controller

Open `turret_manual_control.ino` in Arduino IDE, install the ESP32 core and Adafruit PWM Servo Driver library, and upload it to your board. Serial Monitor uses **115200 baud / Newline**.

Coordinates are servo pulse widths in microseconds. Speed is pulse change per second, not shaft speed.

| Command | Action |
| --- | --- |
| `s 200` | Set speed to 200 us/s |
| `p 1300` | Set pan target |
| `t 1350` | Set tilt target |
| `c 1300 1370` | Set pan and tilt together |
| `c 1300 1350 100` | Set both targets and speed |
| `0` | Return to reference pulses |
| `x` | Stop stepping and hold the last outputs; no newline required |
| `?` | Print outputs, targets and speed |

Speed range: 1–2500 us/s; default: 2500 us/s. `s 0` is rejected. Speed and targets reset on reboot. Startup commands the reference pulses directly.

| Setting | Tilt | Pan |
| --- | --- | --- |
| PCA9685 channel | 0 | 1 |
| Minimum | 400 us | 420 us |
| Reference | 1370 us | 1270 us |
| Maximum | 1510 us | 2850 us |

SDA: GPIO 21. SCL: GPIO 22. PWM: 50 Hz. Change constants near the top of the sketch for a different mechanism. Check clearance before using these limits.

The ramp updates every 20 ms and retains fractional steps. Each axis moves independently at the selected rate; different distances finish at different times. Delayed updates do not cause a catch-up burst. Status timing measures command processing, not physical arrival.

This sketch has no managed-command timeout and does not accept the Python panel's `m` protocol. Use the separate `TurretController` sketch for that panel.

Run the host checks from the repository root with Python and `g++` installed:

```sh
python firmware/turret_manual_control/turret_manual_control/tests/check.py
```

These checks use Arduino/PWM stubs. Compile with the actual ESP32 core and verify on hardware before use.
