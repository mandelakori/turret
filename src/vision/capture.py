"""Camera ingestion with one replaceable frame slot and a host receive clock."""

from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class Frame:
    sequence: int
    received_s: float
    image: object


class LatestFrame:
    """Thread drains VideoCapture while inference works on its own image copy.

    This bounds only OUR application buffer. Driver, decoder, HTTP and camera
    queues may still add delay. received_s is host decode/read completion, not
    exposure time, so its age is a lower bound on true capture-to-control age.
    """

    def __init__(self, source, capture_factory=None):
        if capture_factory is None:
            import cv2 as cv

            capture_factory = cv.VideoCapture
        self.cap = capture_factory(source)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError(f"Cannot open camera source: {source}")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._latest = None
        self.failed = False
        self.error = None
        self._worker = threading.Thread(target=self._read, daemon=True)
        self._worker.start()

    def _read(self):
        sequence = 0
        try:
            while not self._stop.is_set():
                ok, image = self.cap.read()
                if not ok:
                    self.failed = True
                    break
                sequence += 1
                item = Frame(sequence, time.perf_counter(), image)
                with self._lock:
                    self._latest = item
        except Exception as exc:
            # A worker exception cannot propagate into the GUI thread. Publish
            # its message and failure state so the caller exits instead of waiting
            # forever for a frame that will never arrive.
            self.error = str(exc)
            self.failed = True
        finally:
            self.cap.release()

    def newest(self, after_sequence=0):
        with self._lock:
            item = self._latest
            if item is None or item.sequence <= after_sequence:
                return None
            return Frame(item.sequence, item.received_s, item.image.copy())

    def close(self):
        self._stop.set()
        self._worker.join(timeout=1.0)
        # A backend can block inside read(). Do not release it from a second
        # thread; the daemon owns release and exits when its read returns.
        return not self._worker.is_alive()
