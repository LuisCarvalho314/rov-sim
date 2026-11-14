"""Reject timestamp-fresh frames rendered at a stale vehicle pose."""
import unittest
import numpy as np
from compare_camera_backends import wall_range_check


class CameraMotionTests(unittest.TestCase):
    def test_wall_check_rejects_one_frame_old_camera_pose(self):
        k = np.array([[537.1428833, 0, 376], [0, 537.1428833, 240], [0, 0, 1]])
        transform = np.array([[0, 0, 1, -2.65], [-1, 0, 0, 0], [0, -1, 0, 1.35], [0, 0, 0, 1.]])
        yy, xx = np.indices((480, 752))
        norm = np.sqrt(1 + ((xx + .5 - 376) / k[0, 0])**2 + ((yy + .5 - 240) / k[1, 1])**2)
        pose, cal = {"T_world_optical": {"left": transform}}, {"K": {"left": k}}
        good = {"left_clean_range_m": 6.55 * norm}
        self.assertLess(wall_range_check(good, pose, cal, "left"), 1e-8)
        stale = {"left_clean_range_m": (6.55 + .5/59) * norm}
        with self.assertRaisesRegex(ValueError, "range/orientation error"):
            wall_range_check(stale, pose, cal, "left")


if __name__ == "__main__":
    unittest.main()
