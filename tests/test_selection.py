import unittest
from tracking.selection import TargetSelector


def target(x, score=0.8, cls=0):
    return {"centre": (x, 100), "confidence": score, "class_id": cls}


class SelectionTests(unittest.TestCase):
    def test_acquisition_is_by_confidence_not_class_id(self):
        selector = TargetSelector()
        self.assertEqual(
            selector.choose([target(10, 0.5, 0), target(200, 0.9, 3)], 0)["class_id"], 3
        )

    def test_reordered_detections_keep_nearby_observation(self):
        selector = TargetSelector()
        selector.choose([target(100)], 0)
        self.assertEqual(
            selector.choose([target(500, 0.99), target(105, 0.7)], 0.1)["centre"],
            (105, 100),
        )

    def test_no_prediction_across_loss_and_reacquire_after_timeout(self):
        selector = TargetSelector()
        selector.choose([target(100)], 0)
        self.assertIsNone(selector.choose([target(500)], 0.1))
        self.assertIsNone(selector.choose([], 0.2))
        self.assertEqual(selector.choose([target(500)], 0.6)["centre"], (500, 100))
