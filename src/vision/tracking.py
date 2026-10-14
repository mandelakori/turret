"""One-frame detection/segmentation adapter. Temporal association lives elsewhere.

The historical function name `tracking` is retained for compatibility, but it
never estimates velocity or object identity. Importing this module does not
load a model, download weights, or open a camera.
"""

from pathlib import Path
from config import PROJECT_ROOT, load_config


class Detector:
    def __init__(self, model_path=None, confidence=0.5, classes=None):
        from ultralytics import YOLO

        cfg = load_config()["vision"]
        path = Path(model_path) if model_path else PROJECT_ROOT / cfg["model"]
        if not path.is_file():
            raise FileNotFoundError(
                f"Model not found: {path}; provide local weights explicitly"
            )
        self.model = YOLO(str(path))
        self.confidence = confidence
        self.classes = set(cfg["classes"] if classes is None else classes)

    def detect(self, frame):
        # Request masks in original-image dimensions. Resizing an arbitrary
        # letterboxed mask without undoing padding would move its centroid.
        results = self.model.predict(
            frame, conf=self.confidence, retina_masks=True, verbose=False
        )
        return observations_from_results(results, frame.shape[:2], self.classes)


def observations_from_results(results, image_shape, allowed_classes):
    """Extract frame-pixel centroids and scores in [0,1], without altering input.

    Segmentation centroid uses binary mask moments. Detection-only models use
    bounding-box centres. A mismatched mask is rejected, not silently stretched.
    CPU transfer before NumPy conversion also supports GPU inference results.
    """
    import numpy as np

    height, width = image_shape
    targets = []
    for result in results:
        if result.boxes is None:
            continue
        boxes = result.boxes.xyxy.cpu().numpy()
        labels = result.boxes.cls.cpu().numpy()
        scores = result.boxes.conf.cpu().numpy()
        masks = result.masks.data.cpu().numpy() if result.masks is not None else None
        if masks is not None and masks.shape[1:] != (height, width):
            raise ValueError(
                "Mask/frame shape mismatch; use retina_masks=True with a compatible Ultralytics version"
            )
        for i, (box, label, score) in enumerate(zip(boxes, labels, scores)):
            name = result.names[int(label)]
            if allowed_classes and name not in allowed_classes:
                continue
            x1, y1, x2, y2 = map(float, box)
            if masks is not None:
                selected = masks[i] > 0.5
                ys, xs = np.nonzero(selected)
                if not len(xs):
                    continue
                # Mean pixel coordinates equal m10/m00 and m01/m00 for a binary mask.
                centre = (float(xs.mean()), float(ys.mean()))
                method = "mask_centroid"
            else:
                centre = ((x1 + x2) / 2, (y1 + y2) / 2)
                method = "box_centre"
            targets.append(
                {
                    "centre": centre,
                    "class_id": int(label),
                    "class_name": name,
                    "confidence": float(score),
                    "box": (x1, y1, x2, y2),
                    "centre_method": method,
                }
            )
    return sorted(targets, key=lambda t: t["confidence"], reverse=True)


def draw_targets(frame, targets):
    """Draw on a display copy; inference always receives the clean image."""
    import cv2 as cv

    for t in targets:
        x1, y1, x2, y2 = map(round, t["box"])
        cx, cy = map(round, t["centre"])
        cv.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 0), 2)
        cv.drawMarker(frame, (cx, cy), (0, 0, 255), cv.MARKER_CROSS, 12, 2)
        cv.putText(
            frame,
            f'{t["class_name"]} {t["confidence"]:.0%}',
            (x1, max(15, y1 - 5)),
            cv.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 180, 0),
            1,
        )


_default_detector = None


def tracking(frame):
    """Legacy entry point; lazy model load. Returns confidence as 0..1 now."""
    global _default_detector
    if _default_detector is None:
        _default_detector = Detector()
    return _default_detector.detect(frame)
