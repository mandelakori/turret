import unittest
from types import SimpleNamespace
import numpy as np
from vision.tracking import observations_from_results


class Tensor:
    def __init__(self, value):
        self.value = np.asarray(value)

    def cpu(self):
        return self

    def numpy(self):
        return self.value


def result(mask=None):
    boxes = SimpleNamespace(
        xyxy=Tensor([[1, 1, 5, 3]]), cls=Tensor([0]), conf=Tensor([0.9])
    )
    return SimpleNamespace(
        boxes=boxes,
        masks=None if mask is None else SimpleNamespace(data=Tensor(mask)),
        names={0: "person"},
    )


class VisionTests(unittest.TestCase):
    def test_mask_pixel_centroid_and_score_units(self):
        mask = np.zeros((1, 4, 6))
        mask[0, 1:3, 2:5] = 1
        t = observations_from_results([result(mask)], (4, 6), {"person"})[0]
        self.assertEqual(t["centre"], (3, 1.5))
        self.assertEqual(t["confidence"], 0.9)

    def test_detection_model_uses_box_centre(self):
        t = observations_from_results([result()], (4, 6), {"person"})[0]
        self.assertEqual(t["centre"], (3, 2))
        self.assertEqual(t["centre_method"], "box_centre")

    def test_mismatched_mask_fails_explicitly(self):
        with self.assertRaises(ValueError):
            observations_from_results([result(np.zeros((1, 2, 3)))], (4, 6), {"person"})

    def test_empty_mask_and_excluded_class(self):
        self.assertEqual(
            observations_from_results(
                [result(np.zeros((1, 4, 6)))], (4, 6), {"person"}
            ),
            [],
        )
        self.assertEqual(observations_from_results([result()], (4, 6), {"dog"}), [])
