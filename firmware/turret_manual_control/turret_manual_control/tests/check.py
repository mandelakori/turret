"""Build and run host firmware checks without leaving compiled artifacts."""
from pathlib import Path
import subprocess
import tempfile

tests = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="turret-manual-tests-") as temporary:
    executable = Path(temporary) / "firmware_test"
    subprocess.run([
        "g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
        "-I", str(tests / "firmware_stubs"),
        str(tests / "firmware_test.cpp"), "-o", str(executable),
    ], check=True)
    subprocess.run([str(executable)], check=True)
