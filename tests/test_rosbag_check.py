"""CPU checks of check_pass with a fake rosbag2 reader (no ROS, no Kit)."""
from __future__ import annotations

import pickle
import tempfile
import unittest
from pathlib import Path

try:
    import rosbag_fakes as fakes
except ImportError:  # Run as tests.test_rosbag_check from the repository root.
    from tests import rosbag_fakes as fakes
from rov_sim.rosbag import contract
from rov_sim.rosbag.check import check_pass
from rov_sim.rosbag.writer import PassBagWriter

FRAMES = 3


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="rov mcap check ")
        self.addCleanup(self.folder.cleanup)
        self.run_dir = Path(self.folder.name)
        self.deps = fakes.make_deps()
        self.calibration = fakes.calibration()
        writer = PassBagWriter(self.run_dir, "before", self.deps, self.calibration, 30, "none", {},
                               contract.custom_data("abc", "0" * 64, "camera-sensor", "before", 30))
        for index in range(FRAMES):
            writer.write_frame(index, fakes.frames(), fakes.poses(index))
        writer.close()
        self.staging = writer.staging

    def check(self, frames=FRAMES):
        return check_pass(self.staging, self.deps, self.calibration, frames, 30)

    def test_complete_bag_has_no_problems_and_closes_reader(self):
        self.assertEqual(self.check(), [])
        self.assertTrue(fakes.FakeReader.instances[-1].closed)

    def test_missing_frame(self):
        self.assertEqual(self.check(frames=FRAMES + 1),
                         [f"1 expected stamp(s) missing from every topic, first {contract.stamp_ns(FRAMES, 30)}"])

    def test_dropped_message_leaves_incomplete_bundle(self):
        stamp = contract.stamp_ns(1, 30)
        fakes.tamper(self.staging, lambda topics, records: (topics, [r for r in records
                                                                     if not (r[0] == "/stereo/right/image_raw" and r[2] == stamp)]))
        self.assertEqual(self.check(), [f"stamp {stamp} lacks /stereo/right/image_raw"])

    def test_wrong_encoding(self):
        fakes.tamper(self.staging, fakes.edit_messages("/stereo/left/image_raw", lambda m: setattr(m, "encoding", "rgb8")))
        problems = self.check()
        self.assertEqual(len(problems), 1)  # Reported once, not per frame.
        self.assertIn("rgb8", problems[0])

    def test_wrong_header_stamp(self):
        def shift(message):
            message.header.stamp.nanosec += 1

        fakes.tamper(self.staging, fakes.edit_messages("/ground_truth/pose", shift))
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn("differs from log time", problems[0])

    def test_wrong_log_time(self):
        def edit(topics, records):
            return topics, [(name, data, recv + (5 if name == "/tf" else 0), send) for name, data, recv, send in records]

        fakes.tamper(self.staging, edit)
        problems = self.check()
        self.assertTrue(any("differs from log time" in p for p in problems), problems)
        self.assertTrue(any("unexpected stamp" in p for p in problems), problems)

    def test_tf_differs_from_pose(self):
        def move(message):
            message.transforms[0].transform.translation.x += 0.001

        fakes.tamper(self.staging, fakes.edit_messages("/tf", move))
        problems = self.check()
        self.assertEqual(problems, [f"/tf differs from /ground_truth/pose at {FRAMES} stamp(s), first {contract.EPOCH_NS}"])

    def test_wrong_camera_info_and_frame_id(self):
        def corner_convention(message):
            message.k[2] += 0.5

        fakes.tamper(self.staging, fakes.edit_messages("/stereo/left/camera_info", corner_convention))
        fakes.tamper(self.staging, fakes.edit_messages("/stereo/right/image_raw",
                                                       lambda m: setattr(m.header, "frame_id", "camera")))
        problems = self.check()
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(any("/stereo/left/camera_info differs" in p for p in problems))
        self.assertTrue(any("frame_id 'camera'" in p for p in problems))

    def test_tf_static_volatile_qos(self):
        def volatile(topics, records):
            for topic in topics:
                if topic.name == "/tf_static":
                    topic.offered_qos_profiles = [fakes.QoS(1).keep_last(1).reliable().durability_volatile()]
            return topics, records

        fakes.tamper(self.staging, volatile)
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn("/tf_static QoS is durability=volatile", problems[0])

    def test_wrong_topic_type_and_missing_topic(self):
        def edit(topics, records):
            topics = [t for t in topics if t.name != "/tf"]
            for topic in topics:
                if topic.name == "/ground_truth/pose":
                    topic.type = "geometry_msgs/msg/PoseWithCovarianceStamped"
            return topics, records

        fakes.tamper(self.staging, edit)
        problems = self.check()
        self.assertIn("topic /tf is missing", problems)
        self.assertTrue(any("PoseWithCovarianceStamped" in p for p in problems))

    def test_reader_is_closed_when_reading_raises(self):
        fakes.FakeReader.fail_after = 4
        with self.assertRaisesRegex(OSError, "injected"):
            self.check()
        self.assertTrue(fakes.FakeReader.instances[-1].closed)

    def test_pickle_roundtrip_is_the_written_data(self):
        # Guards the fake: check_pass must see exactly what the writer produced.
        path = sorted(self.staging.glob("*.mcap"))[0]
        self.assertEqual(len(pickle.loads(path.read_bytes())["records"]), FRAMES * fakes.TOPIC_COUNT)


if __name__ == "__main__":
    unittest.main()
