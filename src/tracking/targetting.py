"""Camera preview with detections and virtual pulse targets; no actuator output."""

import argparse
import csv
import time
from pathlib import Path
from config import load_config
from control.controller import ControlSettings, calculate_correction, effective_error
from control.pan_tilt import AxisLimits, PulseTargets
from tracking.selection import TargetSelector


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", default="0", help="Webcam index or HTTP/MJPEG stream URL"
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--no-mirror", action="store_true")
    parser.add_argument("--log", default="data/preview.csv")
    args = parser.parse_args(argv)
    import cv2 as cv
    from vision.capture import LatestFrame
    from vision.tracking import Detector, draw_targets

    cfg = load_config()
    c = cfg["control"]
    settings = ControlSettings(
        c["gain_us_per_second_per_pixel"], c["max_rate_us_per_second"], c["max_dt_s"]
    )
    targets = PulseTargets(AxisLimits(**cfg["pan"]), AxisLimits(**cfg["tilt"]))
    mirrored = cfg["vision"]["mirror"] and not args.no_mirror
    pan_sign = c["pan_sign_mirrored"] if mirrored else -c["pan_sign_mirrored"]
    detector = Detector(
        args.model, cfg["vision"]["confidence"], cfg["vision"]["classes"]
    )
    selector = TargetSelector()
    source = int(args.source) if args.source.isdigit() else args.source
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to silently erase an earlier experiment.
    stream = log_path.open("x", newline="", encoding="utf-8")
    capture = None
    try:
        capture = LatestFrame(source)
        writer = csv.writer(stream)
        writer.writerow(
            [
                "frame_id",
                "received_s",
                "processing_s",
                "host_age_s",
                "dt_s",
                "dt_used_s",
                "status",
                "effective_x_px",
                "effective_y_px",
                "pan_target_us",
                "tilt_target_us",
            ]
        )
        sequence = 0
        previous = None
        while True:
            item = capture.newest(sequence)
            if item is None:
                if capture.failed:
                    print(f"Camera stopped: {capture.error or 'no more frames'}")
                    break
                if cv.waitKey(1) & 0xFF == ord("q"):
                    break
                time.sleep(0.001)
                continue
            sequence = item.sequence
            image = cv.flip(item.image, 1) if mirrored else item.image
            start = time.perf_counter()
            observations = detector.detect(image)
            now = time.perf_counter()
            age = now - item.received_s
            target = selector.choose(observations, now)
            dt = 0.0 if previous is None else now - previous
            previous = now
            ex = ey = dt_used = 0.0
            status = "no_target"
            if age > c["max_observation_age_s"]:
                status = "stale_host_observation"
            elif target:
                height, width = image.shape[:2]
                ex = effective_error(target["centre"][0] - width / 2, c["deadzone_px"])
                ey = effective_error(target["centre"][1] - height / 2, c["deadzone_px"])
                correction = calculate_correction(ex, ey, dt, settings)
                dt_used = correction.dt_used_s
                targets.advance(correction, pan_sign, c["tilt_sign"])
                status = "preview_only"
            # No detection or stale data => no additional target integration.
            pan, tilt = targets.command()
            writer.writerow(
                [
                    sequence,
                    item.received_s,
                    now - start,
                    age,
                    dt,
                    dt_used,
                    status,
                    ex,
                    ey,
                    pan,
                    tilt,
                ]
            )
            stream.flush()
            display = image.copy()
            draw_targets(display, observations)
            height, width = image.shape[:2]
            cx, cy = width // 2, height // 2
            d = round(c["deadzone_px"])
            cv.rectangle(display, (cx - d, cy - d), (cx + d, cy + d), (0, 255, 255), 1)
            cv.putText(
                display,
                f"PREVIEW p={pan} t={tilt} | {status}",
                (10, 25),
                cv.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                1,
            )
            cv.imshow("Turret preview - q quit, r reset virtual targets", display)
            key = cv.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("r"):
                targets.reset()
    finally:
        stream.close()
        if capture is not None and not capture.close():
            print(
                "Camera backend still blocked in read; worker will exit with the process."
            )
        cv.destroyAllWindows()


if __name__ == "__main__":
    main()
