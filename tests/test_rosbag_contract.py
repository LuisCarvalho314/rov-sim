"""CPU checks for the Isaac stereo MCAP message contract (no ROS, no Kit)."""
from __future__ import annotations

import math
import unittest

import numpy as np

from rov_sim.rosbag import contract

FX = 752 * 24.0 / 33.6


def calibration(width=752, height=480, baseline=0.38, rig=None):
    k = [[FX, 0.0, width / 2], [0.0, FX, height / 2], [0.0, 0.0, 1.0]]
    return {"resolution_wh": [width, height], "baseline_m": baseline, "K": {"left": k, "right": k},
            "distortion_coefficients": [0, 0, 0, 0, 0],
            "T_leftOptical_rightOptical": rig or [[1, 0, 0, baseline], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}


def rotation(axis, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
            "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]


def homogeneous(R, t=(0.0, 0.0, 0.0)):
    return [[*R[0], t[0]], [*R[1], t[1]], [*R[2], t[2]], [0, 0, 0, 1]]


def matrix_from_quaternion(x, y, z, w):
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


class StampTests(unittest.TestCase):
    def test_hand_values_and_epoch(self):
        self.assertEqual(contract.EPOCH_NS, 1_767_225_600_000_000_000)
        self.assertEqual(contract.stamp_ns(0, 30), contract.EPOCH_NS)
        self.assertEqual(contract.stamp_ns(1, 30), contract.EPOCH_NS + 33_333_333)
        self.assertEqual(contract.stamp_ns(3, 30), contract.EPOCH_NS + 100_000_000)
        self.assertEqual(contract.stamp_parts(contract.stamp_ns(31, 30)), (1_767_225_601, 33_333_333))

    def test_integer_exactness_over_ten_thousand_frames(self):
        stamps = contract.expected_stamps(10_000, 30)
        self.assertTrue(all(isinstance(value, int) for value in stamps))
        self.assertEqual(stamps[9_999], contract.EPOCH_NS + 9_999 * 10**9 // 30)
        self.assertEqual(stamps[3_000], contract.EPOCH_NS + 100 * 10**9)
        self.assertTrue(all(b > a for a, b in zip(stamps, stamps[1:])))

    def test_fps_must_be_positive_int(self):
        for fps in (30.0, "30", True):
            with self.assertRaises(TypeError):
                contract.stamp_ns(1, fps)
        with self.assertRaises(ValueError):
            contract.stamp_ns(1, 0)
        with self.assertRaises(ValueError):
            contract.stamp_ns(-1, 30)


class CameraInfoTests(unittest.TestCase):
    def test_pixel_centre_shift_and_projection(self):
        left = contract.camera_info_fields(calibration(), "left")
        right = contract.camera_info_fields(calibration(), "right")
        for info in (left, right):
            self.assertEqual((info["width"], info["height"]), (752, 480))
            self.assertEqual(info["k"][2], 375.5)
            self.assertEqual(info["k"][5], 239.5)
            self.assertEqual(info["d"], [0.0] * 5)
            self.assertEqual(info["r"], [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])
            self.assertEqual(info["distortion_model"], "plumb_bob")
            self.assertEqual((info["p"][2], info["p"][6]), (375.5, 239.5))
        self.assertEqual(left["p"][3], 0.0)
        self.assertAlmostEqual(right["p"][3], -FX * 0.38, places=12)
        self.assertEqual((left["frame_id"], right["frame_id"]), (contract.LEFT_FRAME, contract.RIGHT_FRAME))

    def test_nonzero_distortion_and_bad_side_are_rejected(self):
        bad = calibration()
        bad["distortion_coefficients"] = [0.1, 0, 0, 0, 0]
        with self.assertRaises(ValueError):
            contract.camera_info_fields(bad, "left")
        with self.assertRaises(ValueError):
            contract.camera_info_fields(calibration(), "centre")


class PoseTests(unittest.TestCase):
    def assertQuaternionMatches(self, R, quaternion):
        self.assertGreaterEqual(quaternion[3], 0.0)
        self.assertAlmostEqual(sum(value * value for value in quaternion), 1.0, places=12)
        np.testing.assert_allclose(matrix_from_quaternion(*quaternion), R, atol=1e-12)

    def test_identity(self):
        xyz, xyzw = contract.pose_fields(homogeneous(rotation("x", 0), (1.0, -2.0, 0.5)))
        self.assertEqual(xyz, [1.0, -2.0, 0.5])
        self.assertEqual(xyzw, [0.0, 0.0, 0.0, 1.0])

    def test_ninety_degrees_about_each_axis(self):
        half = math.sqrt(0.5)
        for index, axis in enumerate("xyz"):
            R = rotation(axis, 90)
            _, xyzw = contract.pose_fields(homogeneous(R))
            expected = [0.0, 0.0, 0.0, half]
            expected[index] = half
            np.testing.assert_allclose(xyzw, expected, atol=1e-12)
            self.assertQuaternionMatches(R, xyzw)

    def test_negative_w_is_normalized_and_every_branch_is_correct(self):
        # 200 degrees about each axis takes Shepperd's x/y/z branch with w < 0 before the sign fix;
        # 180 degrees has w = 0; the optical rig rotation is the production case.
        cases = [rotation(axis, angle) for axis in "xyz" for angle in (180, 200, -170, 270)]
        cases.append([[0, -1, 0], [0, 0, -1], [1, 0, 0]])
        for R in cases:
            _, xyzw = contract.pose_fields(homogeneous(R))
            self.assertQuaternionMatches(R, xyzw)

    def test_non_4x4_is_rejected(self):
        with self.assertRaises(ValueError):
            contract.pose_fields([[1, 0, 0], [0, 1, 0], [0, 0, 1]])


class TfStaticTests(unittest.TestCase):
    def test_baseline_along_left_optical_x(self):
        fields = contract.tf_static_fields(calibration())
        self.assertEqual(fields["translation"], [0.38, 0.0, 0.0])
        self.assertEqual(fields["rotation_xyzw"], [0.0, 0.0, 0.0, 1.0])
        self.assertEqual((fields["frame_id"], fields["child_frame_id"]), (contract.LEFT_FRAME, contract.RIGHT_FRAME))

    def test_rotated_rig_is_rejected(self):
        with self.assertRaises(ValueError):
            contract.tf_static_fields(calibration(rig=homogeneous(rotation("y", 0.01), (0.38, 0, 0))))


class ImageTests(unittest.TestCase):
    def test_known_colour_pixel_and_contiguity(self):
        rgba = np.zeros((480, 752, 4), np.uint8)
        rgba[7, 11] = (200, 30, 90, 255)
        bgr = contract.rgba_to_bgr8(rgba)
        self.assertEqual(bgr.shape, (480, 752, 3))
        self.assertEqual(bgr.dtype, np.uint8)
        self.assertEqual(tuple(bgr[7, 11]), (90, 30, 200))
        self.assertTrue(bgr.flags["C_CONTIGUOUS"])
        # A non-contiguous input view still produces a contiguous result.
        view = contract.rgba_to_bgr8(rgba[:, ::2])
        self.assertTrue(view.flags["C_CONTIGUOUS"])
        self.assertEqual(tuple(view[7, 5]), (0, 0, 0))


class MetadataTests(unittest.TestCase):
    def test_custom_data_keys_are_strings(self):
        data = contract.custom_data("abc123", "f" * 64, "camera-sensor", "before", 30)
        self.assertEqual(set(data), {"rov_sim.format", "rov_sim.format_version", "rov_sim.writer_commit",
                                     "rov_sim.config_sha256", "rov_sim.backend", "rov_sim.pass",
                                     "rov_sim.epoch_ns", "rov_sim.fps"})
        self.assertTrue(all(isinstance(value, str) for value in data.values()))
        self.assertEqual(data["rov_sim.format"], "isaac-stereo-mcap")
        self.assertEqual(data["rov_sim.format_version"], "1")
        self.assertEqual(data["rov_sim.epoch_ns"], str(contract.EPOCH_NS))

    def test_topics_qos_and_order(self):
        self.assertEqual(contract.TOPIC_NAMES, ("/stereo/left/image_raw", "/stereo/right/image_raw",
                                                "/stereo/left/camera_info", "/stereo/right/camera_info",
                                                "/ground_truth/pose", "/tf_static", "/tf"))
        self.assertEqual(contract.QOS["/tf_static"], {"reliability": "reliable", "durability": "transient_local", "depth": 1})
        for name in contract.TOPIC_NAMES:
            if name != "/tf_static":
                self.assertEqual(contract.QOS[name], {"reliability": "reliable", "durability": "volatile", "depth": 10})


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.expected = contract.expected_stamps(3, 30)

    def complete(self):
        return {name: list(self.expected) for name in contract.TOPIC_NAMES}

    def test_complete(self):
        self.assertEqual(contract.bundle_problems(self.complete(), self.expected), [])

    def test_missing_frame(self):
        stamps = {name: self.expected[:2] for name in contract.TOPIC_NAMES}
        problems = contract.bundle_problems(stamps, self.expected)
        self.assertEqual(len(problems), 1)
        self.assertIn("missing", problems[0])

    def test_duplicate(self):
        stamps = self.complete()
        stamps["/tf"].append(self.expected[1])
        self.assertEqual(contract.bundle_problems(stamps, self.expected), ["/tf: 1 duplicate stamp(s)"])

    def test_extra_stamp(self):
        stamps = self.complete()
        extra = contract.stamp_ns(3, 30)
        for name in stamps:
            stamps[name].append(extra)
        problems = contract.bundle_problems(stamps, self.expected)
        self.assertEqual(problems, [f"1 unexpected stamp(s), first {extra}"])

    def test_incomplete_bundle_and_unknown_topic(self):
        stamps = self.complete()
        stamps["/stereo/right/image_raw"].remove(self.expected[2])
        del stamps["/tf_static"]
        stamps["/clock"] = [self.expected[0]]
        problems = contract.bundle_problems(stamps, self.expected)
        self.assertIn("unexpected topic /clock", problems)
        self.assertIn(f"stamp {self.expected[0]} lacks /tf_static", problems)
        self.assertIn(f"stamp {self.expected[2]} lacks /stereo/right/image_raw, /tf_static", problems)


if __name__ == "__main__":
    unittest.main()
