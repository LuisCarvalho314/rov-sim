"""CPU checks of PassBagWriter with a fake rosbag2_py (no ROS, no Kit)."""
from __future__ import annotations

import json
import pickle
import tempfile
import unittest
from pathlib import Path

try:
    import rosbag_fakes as fakes
except ImportError:  # Run as tests.test_rosbag_writer from the repository root.
    from tests import rosbag_fakes as fakes
from rov_sim.rosbag import contract
from rov_sim.rosbag.writer import PassBagWriter


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="rov mcap ")
        self.addCleanup(self.folder.cleanup)
        self.run_dir = Path(self.folder.name)
        self.deps = fakes.make_deps()
        self.status = {"state": "running_before", "completed_frames": {}}
        self.calibration = fakes.calibration()

    def open(self, storage="none", pass_name="before"):
        return PassBagWriter(self.run_dir, pass_name, self.deps, self.calibration, 30, storage, self.status,
                             contract.custom_data("abc", "0" * 64, "camera-sensor", pass_name, 30))

    def saved(self):
        return json.loads((self.run_dir / "status.json").read_text(encoding="utf-8"))

    def write(self, writer, count):
        for index in range(count):
            writer.write_frame(index, fakes.frames(), fakes.poses(index))

    def test_staging_uri_preset_and_custom_data(self):
        for storage, preset in (("none", ""), ("zstd", "zstd_fast")):
            with self.subTest(storage):
                self.open(storage, pass_name=storage)
                options = fakes.FakeWriter.instances[-1].storage
                self.assertEqual(Path(options.uri), self.run_dir / "mcap" / ".staging" / storage)
                self.assertEqual(options.storage_id, "mcap")
                self.assertEqual(options.storage_preset_profile, preset)
                self.assertEqual(options.custom_data["rov_sim.pass"], storage)
                self.assertEqual(fakes.FakeWriter.instances[-1].converter.formats, ("cdr", "cdr"))
        with self.assertRaises(ValueError):
            self.open("lz4", pass_name="after")

    def test_seven_topics_and_tf_static_qos(self):
        self.open()
        topics = fakes.FakeWriter.instances[0].topics
        self.assertEqual([(t.id, t.name, t.type, t.serialization_format) for t in topics],
                         [(i, name, ros_type, "cdr") for i, (name, ros_type) in enumerate(contract.TOPICS)])
        for topic in topics:
            (qos,) = topic.offered_qos_profiles
            self.assertEqual(qos.reliability, fakes.Reliability.RELIABLE)
            if topic.name == "/tf_static":
                self.assertEqual((qos.durability, qos.depth, qos.history_depth), (fakes.Durability.TRANSIENT_LOCAL, 1, 1))
            else:
                self.assertEqual((qos.durability, qos.depth, qos.history_depth), (fakes.Durability.VOLATILE, 10, 10))

    def test_opening_saves_writing_before_the_first_frame(self):
        writer = self.open()
        self.assertEqual(fakes.FakeWriter.instances[0].calls[-1], "create_topic")
        saved = self.saved()["mcap"]["before"]
        self.assertEqual(saved["state"], "writing")
        self.assertEqual(saved["message_counts"], {name: 0 for name in contract.TOPIC_NAMES})
        self.assertIs(self.status["mcap"]["before"], writer.entry)

    def test_seven_writes_per_frame_in_order_with_log_equal_publish_equal_stamp(self):
        writer = self.open()
        self.write(writer, 3)
        records = fakes.FakeWriter.instances[0].records
        self.assertEqual(len(records), 21)
        for index in range(3):
            stamp = contract.stamp_ns(index, 30)
            frame = records[index * 7:(index + 1) * 7]
            self.assertEqual([r[0] for r in frame], list(contract.TOPIC_NAMES))
            for topic, data, recv, send in frame:
                self.assertEqual((recv, send), (stamp, stamp))
                message = pickle.loads(data)
                header = message.transforms[0].header if topic in ("/tf", "/tf_static") else message.header
                self.assertEqual(header.stamp.sec * 10**9 + header.stamp.nanosec, stamp)
        image = pickle.loads(records[0][1])
        self.assertEqual((image.encoding, image.step, image.is_bigendian, image.width, image.height),
                         ("bgr8", 3 * 752, 0, 752, 480))
        self.assertEqual(tuple(image.data[:3]), (90, 30, 200))
        self.assertEqual(writer.entry["message_counts"], {name: 3 for name in contract.TOPIC_NAMES})

    def test_wrong_image_shape_is_rejected(self):
        writer = self.open()
        with self.assertRaisesRegex(ValueError, "expected uint8"):
            writer.write_frame(0, fakes.frames(width=640), fakes.poses(0))

    def test_close_does_not_rename_and_records_size(self):
        writer = self.open()
        self.write(writer, 2)
        writer.close()
        staging = self.run_dir / "mcap" / ".staging" / "before"
        bag = staging / "before_0.mcap"
        self.assertTrue(bag.is_file())
        self.assertFalse((self.run_dir / "mcap" / "before").exists())
        self.assertEqual(writer.entry["bag_bytes"], bag.stat().st_size)
        self.assertEqual(writer.entry["bytes_per_frame"], bag.stat().st_size / 2)
        self.assertEqual(fakes.FakeWriter.instances[0].calls[-1], "close")
        self.assertEqual(self.saved()["mcap"]["before"]["state"], "writing")

    def test_commit_renames_and_completes(self):
        writer = self.open()
        self.write(writer, 1)
        writer.close()
        writer.commit()
        self.assertFalse((self.run_dir / "mcap" / ".staging" / "before").exists())
        self.assertTrue((self.run_dir / "mcap" / "before" / "before_0.mcap").is_file())
        self.assertEqual(self.saved()["mcap"]["before"]["state"], "complete")

    def test_commit_requires_close(self):
        writer = self.open()
        with self.assertRaises(RuntimeError):
            writer.commit()

    def test_check_failed_keeps_staging_and_five_problems(self):
        writer = self.open()
        writer.close()
        writer.mark_check_failed([f"problem {i}" for i in range(8)])
        saved = self.saved()["mcap"]["before"]
        self.assertEqual(saved["state"], "check_failed")
        self.assertEqual(saved["problems"], [f"problem {i}" for i in range(5)])
        self.assertEqual(saved["problem_count"], 8)
        self.assertTrue((self.run_dir / "mcap" / ".staging" / "before").is_dir())
        self.assertFalse((self.run_dir / "mcap" / "before").exists())

    def test_abort_keeps_staging_and_never_renames(self):
        writer = self.open()
        self.write(writer, 1)
        writer.abort(OSError(28, "No space left on device"))
        saved = self.saved()["mcap"]["before"]
        self.assertEqual(saved["state"], "failed")
        self.assertIn("No space left on device", saved["error"])
        self.assertEqual(fakes.FakeWriter.instances[0].calls[-1], "close")
        self.assertTrue((self.run_dir / "mcap" / ".staging" / "before").is_dir())
        self.assertFalse((self.run_dir / "mcap" / "before").exists())

    def test_abort_suppresses_close_error(self):
        writer = self.open()

        def broken_close():
            raise OSError("close failed")

        fakes.FakeWriter.instances[0].close = broken_close
        writer.abort(RuntimeError("original"))
        self.assertEqual(writer.entry["error"], "RuntimeError: original")

    def test_abort_is_a_no_op_after_commit_or_check_failure(self):
        committed = self.open()
        committed.close()
        committed.commit()
        committed.abort(RuntimeError("late"))
        self.assertEqual(committed.entry["state"], "complete")
        rejected = self.open(pass_name="after")
        rejected.close()
        rejected.mark_check_failed(["bad"])
        rejected.abort(RuntimeError("late"))
        self.assertEqual(rejected.entry["state"], "check_failed")
        self.assertIsNone(rejected.entry["error"])

    def test_write_exception_propagates(self):
        writer = self.open()
        fakes.FakeWriter.fail_on_write = OSError(28, "No space left on device")
        with self.assertRaises(OSError):
            writer.write_frame(0, fakes.frames(), fakes.poses(0))

    def test_open_failure_marks_the_pass_failed(self):
        (self.run_dir / "mcap" / ".staging" / "before").mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.open()
        self.assertEqual(self.status["mcap"]["before"]["state"], "failed")
        self.assertEqual(self.saved()["mcap"]["before"]["state"], "failed")


if __name__ == "__main__":
    unittest.main()
