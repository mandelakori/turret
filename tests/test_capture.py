import threading
import unittest
import numpy as np
from vision.capture import LatestFrame


class FakeCapture:
    def __init__(self, source):
        self.index = 0
        self.released = threading.Event()

    def isOpened(self):
        return True

    def read(self):
        self.index += 1
        if self.index > 3:
            return False, None
        return True, np.full((2, 2, 3), self.index, dtype=np.uint8)

    def release(self):
        self.released.set()


class CaptureTests(unittest.TestCase):
    def test_latest_slot_skips_old_frames_and_copies_image(self):
        camera = LatestFrame(0, capture_factory=FakeCapture)
        self.assertTrue(camera.cap.released.wait(1))
        item = camera.newest()
        self.assertEqual(item.sequence, 3)
        self.assertIsNone(camera.newest(3))
        item.image[:] = 0
        self.assertEqual(int(camera.newest().image[0, 0, 0]), 3)
        self.assertTrue(camera.close())

        class BrokenCapture(FakeCapture):
            def read(self):
                raise RuntimeError("test camera disconnected")

        # Both an ordinary end-of-stream and an exception must release the
        # source and tell the caller that waiting for another frame is futile.
        camera = LatestFrame(0, capture_factory=BrokenCapture)
        self.assertTrue(camera.cap.released.wait(1))
        self.assertTrue(camera.failed)
        self.assertEqual(camera.error, "test camera disconnected")
        self.assertTrue(camera.close())
