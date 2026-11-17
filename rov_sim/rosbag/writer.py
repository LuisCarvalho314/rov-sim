"""One rosbag2 MCAP bag per capture pass, written synchronously from the capture loop.

Every ROS class comes from ``deps`` (rov_sim.rosbag.deps.load()); this module imports
nothing from ROS, so CPU tests pass fakes in. Pass states in status.json:
writing -> complete | check_failed | failed.
See docs/designs/isaac-stereo-mcap.md ("Writer" and "Output layout and pass states").
"""
from __future__ import annotations

import array
import os
from pathlib import Path

from rov_sim.recording import write_json
from rov_sim.rosbag import contract

STORAGE_PRESETS = {"none": "", "zstd": "zstd_fast"}
MAX_PROBLEMS = 5


def _stamp(header, sec, nanosec):
    header.stamp.sec, header.stamp.nanosec = sec, nanosec


class PassBagWriter:
    def __init__(self, run_dir, pass_name, deps, calibration, fps, storage, status, custom_data):
        if storage not in STORAGE_PRESETS:
            raise ValueError(f"MCAP storage must be one of {sorted(STORAGE_PRESETS)}, got {storage!r}")
        contract.stamp_ns(0, fps)  # Validates fps before anything is created.
        self.run_dir = Path(run_dir)
        self.pass_name = pass_name
        self.deps = deps
        self.calibration = calibration
        self.fps = fps
        self.status = status
        self.staging = self.run_dir / "mcap" / ".staging" / pass_name
        self.final = self.run_dir / "mcap" / pass_name
        self.frames_written = 0
        self.entry = {"state": "writing", "message_counts": {name: 0 for name in contract.TOPIC_NAMES},
                      "problems": [], "error": None, "bag_bytes": None, "bytes_per_frame": None}
        status.setdefault("mcap", {})[pass_name] = self.entry
        self._writer = None
        self._width, self._height = (int(value) for value in calibration["resolution_wh"])
        try:
            self._static = self._static_messages()
            if self.staging.exists() or self.final.exists():
                raise FileExistsError(f"MCAP pass folder already exists: {self.staging} or {self.final}")
            self.staging.parent.mkdir(parents=True, exist_ok=True)
            self._save()
            writer = deps.SequentialWriter()
            # rosbag2 creates the URI directory and names the file <pass>_0.mcap.
            writer.open(deps.StorageOptions(uri=str(self.staging), storage_id="mcap",
                                            storage_preset_profile=STORAGE_PRESETS[storage],
                                            custom_data=dict(custom_data)),
                        deps.ConverterOptions("cdr", "cdr"))
            self._writer = writer
            for topic_id, (name, ros_type) in enumerate(contract.TOPICS):
                writer.create_topic(deps.TopicMetadata(topic_id, name, ros_type, "cdr", [self._qos(name)]))
        except BaseException as error:
            self.abort(error)
            raise

    @property
    def state(self):
        return self.entry["state"]

    def _save(self):
        write_json(self.run_dir / "status.json", self.status)

    def _qos(self, topic):
        spec = contract.QOS[topic]
        qos = self.deps.QoS(spec["depth"]).keep_last(spec["depth"])
        qos = qos.reliable() if spec["reliability"] == "reliable" else qos.best_effort()
        return qos.transient_local() if spec["durability"] == "transient_local" else qos.durability_volatile()

    def _static_messages(self):
        """CameraInfo and /tf_static are identical every frame apart from the stamp."""
        messages = self.deps.messages
        result = {}
        for side, topic in contract.INFO_TOPICS.items():
            fields = contract.camera_info_fields(self.calibration, side)
            info = messages[contract.CAMERA_INFO_TYPE]()
            info.header.frame_id = fields["frame_id"]
            info.width, info.height = fields["width"], fields["height"]
            info.distortion_model = fields["distortion_model"]
            info.d, info.k, info.r, info.p = fields["d"], fields["k"], fields["r"], fields["p"]
            result[topic] = (info, [info.header])
        fields = contract.tf_static_fields(self.calibration)
        transform = self._transform(fields["frame_id"], fields["child_frame_id"],
                                    fields["translation"], fields["rotation_xyzw"])
        result[contract.TF_STATIC] = (messages[contract.TF_TYPE](transforms=[transform]), [transform.header])
        return result

    def _transform(self, parent, child, xyz, xyzw):
        transform = self.deps.messages["geometry_msgs/msg/TransformStamped"]()
        transform.header.frame_id, transform.child_frame_id = parent, child
        t, q = transform.transform.translation, transform.transform.rotation
        t.x, t.y, t.z = xyz
        q.x, q.y, q.z, q.w = xyzw
        return transform

    def _image(self, side, raw_rgba):
        bgr = contract.rgba_to_bgr8(raw_rgba)
        if tuple(bgr.shape) != (self._height, self._width, 3) or str(bgr.dtype) != "uint8":
            raise ValueError(f"{side} image is {bgr.dtype} {tuple(bgr.shape)}, "
                             f"expected uint8 ({self._height}, {self._width}, 3)")
        image = self.deps.messages[contract.IMAGE_TYPE]()
        image.header.frame_id = contract.SIDE_FRAMES[side]
        image.height, image.width = self._height, self._width
        image.encoding, image.is_bigendian, image.step = contract.IMAGE_ENCODING, 0, 3 * self._width
        # array('B') skips the generated setter's per-element validation of ~1M bytes.
        data = array.array("B")
        data.frombytes(bgr)
        image.data = data
        return image

    def write_frame(self, index, raw_rgba_by_side, poses):
        """Write the seven contract messages for frame ``index``, all stamped stamp_ns(index, fps)."""
        if self._writer is None:
            raise RuntimeError(f"MCAP writer for pass {self.pass_name} is not open")
        stamp = contract.stamp_ns(index, self.fps)
        sec, nanosec = contract.stamp_parts(stamp)
        messages = {}
        for side, topic in contract.IMAGE_TOPICS.items():
            image = self._image(side, raw_rgba_by_side[side])
            _stamp(image.header, sec, nanosec)
            messages[topic] = image
        for topic in (*contract.INFO_TOPICS.values(), contract.TF_STATIC):
            message, headers = self._static[topic]
            for header in headers:
                _stamp(header, sec, nanosec)
            messages[topic] = message
        xyz, xyzw = contract.pose_fields(poses["T_world_optical"]["left"])
        pose = self.deps.messages[contract.POSE_TYPE]()
        pose.header.frame_id = contract.MAP_FRAME
        _stamp(pose.header, sec, nanosec)
        p, q = pose.pose.position, pose.pose.orientation
        p.x, p.y, p.z = xyz
        q.x, q.y, q.z, q.w = xyzw
        messages[contract.POSE] = pose
        transform = self._transform(contract.MAP_FRAME, contract.LEFT_FRAME, xyz, xyzw)
        _stamp(transform.header, sec, nanosec)
        messages[contract.TF] = self.deps.messages[contract.TF_TYPE](transforms=[transform])
        serialize = self.deps.serialize_message
        for name in contract.TOPIC_NAMES:
            # write(topic, data, recv_timestamp, send_timestamp): log time = publish time = stamp.
            self._writer.write(name, serialize(messages[name]), stamp, stamp)
            self.entry["message_counts"][name] += 1
        self.frames_written += 1

    def close(self):
        """Close the bag and record its size; the folder stays in .staging/."""
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
        bag_bytes = sum(path.stat().st_size for path in self.staging.glob("*.mcap"))
        self.entry["bag_bytes"] = bag_bytes
        self.entry["bytes_per_frame"] = bag_bytes / self.frames_written if self.frames_written else None
        self._save()

    def commit(self):
        """After a clean check: rename .staging/<pass> to mcap/<pass> and mark it complete."""
        if self._writer is not None:
            raise RuntimeError("close() the MCAP writer before commit()")
        # metadata.yaml lists the file by relative name, so the rename keeps it valid.
        os.rename(self.staging, self.final)
        self.entry["state"] = "complete"
        self._save()

    def mark_check_failed(self, problems):
        self.entry["state"] = "check_failed"
        self.entry["problems"] = [str(problem) for problem in problems[:MAX_PROBLEMS]]
        self.entry["problem_count"] = len(problems)
        self._save()

    def abort(self, error):
        """Mark the pass failed after an error; never renames. A no-op once checked."""
        if self.entry["state"] in ("complete", "check_failed"):
            return
        writer, self._writer = self._writer, None
        if writer is not None:
            try:
                writer.close()
            except Exception:  # The original error is the one worth reporting.
                pass
        self.entry["state"] = "failed"
        self.entry["error"] = f"{type(error).__name__}: {error}"
        try:
            self._save()
        except Exception:  # The caller writes status.json again; keep the original error.
            pass
