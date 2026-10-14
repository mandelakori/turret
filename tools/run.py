"""Stable launcher: python tools/run.py {preview,mouse,simulate}."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"preview", "mouse", "simulate"}:
        print("Usage: python tools/run.py {preview,mouse,simulate} [options]")
        return 2
    mode = sys.argv[1]
    if mode == "preview":
        from tracking.targetting import main as entry
    elif mode == "mouse":
        from control.mouse_panel import main as entry
    else:
        from simulation.pan_tilt_sim import main as entry
    entry(sys.argv[2:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
