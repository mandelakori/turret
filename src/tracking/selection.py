"""A small observation-association baseline; not an object identity tracker."""

import math


class TargetSelector:
    """Acquire by confidence; retain the nearest same-class centre within a gate.

    No Kalman filter, prediction, appearance features, or persistent IDs are
    claimed. A missing/ungated candidate returns None and causes no correction.
    Forget the previous observation after a timeout to allow reacquisition.
    """

    def __init__(self, gate_px=100.0, forget_after_s=0.5):
        self.gate_px, self.forget_after_s = gate_px, forget_after_s
        self.previous = None
        self.last_seen_s = None

    def choose(self, candidates, now_s):
        if (
            self.last_seen_s is not None
            and now_s - self.last_seen_s > self.forget_after_s
        ):
            self.previous = None
        if not candidates:
            return None
        if self.previous is None:
            selected = max(candidates, key=lambda t: (t["confidence"], -t["class_id"]))
        else:
            px, py = self.previous["centre"]
            same = [
                t
                for t in candidates
                if t["class_id"] == self.previous["class_id"]
                and math.hypot(t["centre"][0] - px, t["centre"][1] - py) <= self.gate_px
            ]
            if not same:
                return None
            selected = min(
                same, key=lambda t: math.hypot(t["centre"][0] - px, t["centre"][1] - py)
            )
        self.previous, self.last_seen_s = selected, now_s
        return selected
