"""Compile the actuator sketch against host stubs and run behavior assertions.

This catches C++ syntax/logic errors but does not compile against the ESP32 core
or exercise I2C/PCA9685. An Arduino build and hardware test remain separate gates.
"""

from pathlib import Path
import shutil, subprocess, tempfile

root = Path(__file__).resolve().parents[1]
compiler = shutil.which("g++")
if not compiler:
    raise SystemExit("g++ is required for the host firmware check")
with tempfile.TemporaryDirectory() as temp:
    executable = str(Path(temp) / "firmware_test")
    subprocess.run(
        [
            compiler,
            "-std=c++11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-misleading-indentation",
            "-I",
            str(root / "tests/firmware_stubs"),
            str(root / "tests/firmware_test.cpp"),
            "-o",
            executable,
        ],
        check=True,
    )
    subprocess.run([executable], check=True)
