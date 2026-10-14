"""Manual mouse panel: absolute pulse targets; no detection, camera, or laser.

Dry run by default. Add --port COM5 for USB output. Hold left mouse to request
motion; release to stop stepping. Tilt stays at its reference unless --tilt is
provided. The initial panel covers a small pulse interval around each reference.
"""

import argparse
import time
from config import load_config
from control.pan_tilt import AxisLimits, cursor_to_pulses


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", help="Omit for dry run; use COM5 or /dev/ttyUSB0 for live USB"
    )
    parser.add_argument(
        "--tilt",
        action="store_true",
        help="Also map vertical cursor position to tilt pulses",
    )
    parser.add_argument(
        "--span-us",
        type=int,
        default=200,
        help="Pulse interval on each side of reference (default 200)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.span_us <= 2000:
        parser.error("--span-us must be between 1 and 2000")
    import cv2 as cv
    import numpy as np
    from networking.esp32 import SerialLink

    cfg = load_config()

    def panel_limits(axis):
        a = cfg[axis]
        zero = a["reference_us"]
        return AxisLimits(
            max(a["minimum_us"], zero - args.span_us),
            min(a["maximum_us"], zero + args.span_us),
            zero,
        )

    pan, tilt = panel_limits("pan"), panel_limits("tilt")
    width, height = 640, 480
    mouse = {"x": width / 2, "y": height / 2, "held": False}

    def on_mouse(event, x, y, flags, unused):
        mouse.update(x=x, y=y, held=bool(flags & cv.EVENT_FLAG_LBUTTON))
        if event == cv.EVENT_LBUTTONUP:
            mouse["held"] = False

    title = "Turret manual panel - hold left mouse; release or x to stop; q quit"
    link = None
    was_held = False
    last_send = 0.0
    try:
        link = SerialLink(args.port) if args.port else None
        cv.namedWindow(title, cv.WINDOW_AUTOSIZE)
        cv.setMouseCallback(title, on_mouse)
        print("LIVE USB" if link else "DRY RUN: no serial port is open")
        while True:
            p, t = cursor_to_pulses(mouse["x"], mouse["y"], width, height, pan, tilt)
            if not args.tilt:
                t = cfg["tilt"]["reference_us"]
            held = mouse["held"]
            now = time.monotonic()
            if held and now - last_send >= 0.05:
                if link:
                    link.send_targets(p, t)
                print(f"{'SEND' if link else 'PREVIEW'} pan={p} us tilt={t} us")
                last_send = now
            elif was_held and not held and link:
                link.stop()
            was_held = held
            if link:
                for line in link.read_lines():
                    print(line)
            panel = np.zeros((height, width, 3), dtype=np.uint8)
            cv.putText(
                panel,
                "LIVE USB" if link else "DRY RUN",
                (20, 35),
                cv.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
            )
            cv.putText(
                panel,
                f"Target p={p} us t={t} us",
                (20, 70),
                cv.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
            )
            cv.putText(
                panel,
                "HOLDING MOUSE" if held else "RELEASED: no new motion",
                (20, 105),
                cv.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
            )
            cv.circle(panel, (int(mouse["x"]), int(mouse["y"])), 8, (0, 200, 255), 2)
            cv.imshow(title, panel)
            key = cv.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("x"):
                mouse["held"] = False
                if link:
                    link.stop()
            if cv.getWindowProperty(title, cv.WND_PROP_VISIBLE) < 1:
                break
    finally:
        if link:
            link.close()
        cv.destroyAllWindows()


if __name__ == "__main__":
    main()
