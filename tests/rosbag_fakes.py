"""Fake rosbag2_py/rclpy layer for CPU tests: messages round-trip through pickle in a file.

The fake writer creates the URI directory and <pass>_0.mcap as rosbag2 does, and the
fake reader replays what was written, so writer -> check runs end to end without ROS.
"""
from __future__ import annotations

import copy
import enum
import pickle
from pathlib import Path
from types import SimpleNamespace

from rov_sim.rosbag import contract
from rov_sim.rosbag.deps import RosbagDeps


class Time:
    def __init__(self):
        self.sec, self.nanosec = 0, 0


class Header:
    def __init__(self):
        self.stamp, self.frame_id = Time(), ""


class Vector3:
    def __init__(self):
        self.x = self.y = self.z = 0.0


class Quaternion(Vector3):
    def __init__(self):
        super().__init__()
        self.w = 1.0


class Image:
    def __init__(self):
        self.header = Header()
        self.height = self.width = self.step = self.is_bigendian = 0
        self.encoding, self.data = "", b""


class CameraInfo:
    def __init__(self):
        self.header = Header()
        self.width = self.height = 0
        self.distortion_model, self.d, self.k, self.r, self.p = "", [], [0.0] * 9, [0.0] * 9, [0.0] * 12


class PoseStamped:
    def __init__(self):
        self.header = Header()
        self.pose = SimpleNamespace(position=Vector3(), orientation=Quaternion())


class TransformStamped:
    def __init__(self):
        self.header, self.child_frame_id = Header(), ""
        self.transform = SimpleNamespace(translation=Vector3(), rotation=Quaternion())


class TFMessage:
    def __init__(self, transforms=None):
        self.transforms = list(transforms or [])


MESSAGES = {"sensor_msgs/msg/Image": Image, "sensor_msgs/msg/CameraInfo": CameraInfo,
            "geometry_msgs/msg/PoseStamped": PoseStamped, "geometry_msgs/msg/TransformStamped": TransformStamped,
            "tf2_msgs/msg/TFMessage": TFMessage, "builtin_interfaces/msg/Time": Time}


class Durability(enum.IntEnum):
    TRANSIENT_LOCAL = 1
    VOLATILE = 2


class Reliability(enum.IntEnum):
    RELIABLE = 1
    BEST_EFFORT = 2


class QoS:
    def __init__(self, depth):
        self.depth, self.history_depth, self.durability, self.reliability = depth, None, None, None

    def keep_last(self, depth):
        self.history_depth = depth
        return self

    def reliable(self):
        self.reliability = Reliability.RELIABLE
        return self

    def best_effort(self):
        self.reliability = Reliability.BEST_EFFORT
        return self

    def transient_local(self):
        self.durability = Durability.TRANSIENT_LOCAL
        return self

    def durability_volatile(self):
        self.durability = Durability.VOLATILE
        return self


class StorageOptions:
    def __init__(self, uri, storage_id, storage_preset_profile="", custom_data=None):
        self.uri, self.storage_id = uri, storage_id
        self.storage_preset_profile, self.custom_data = storage_preset_profile, custom_data or {}


class ConverterOptions:
    def __init__(self, input_serialization_format, output_serialization_format):
        self.formats = (input_serialization_format, output_serialization_format)


class TopicMetadata:
    def __init__(self, id, name, type, serialization_format, offered_qos_profiles):
        self.id, self.name, self.type = id, name, type
        self.serialization_format, self.offered_qos_profiles = serialization_format, offered_qos_profiles


class FakeWriter:
    instances = []
    fail_on_write = None  # Exception raised by write() when set.

    def __init__(self):
        self.calls, self.topics, self.records, self.path = [], [], [], None
        FakeWriter.instances.append(self)

    def open(self, storage, converter):
        uri = Path(storage.uri)
        uri.mkdir()  # rosbag2 refuses an existing directory.
        self.path = uri / f"{uri.name}_0.mcap"
        self.storage, self.converter = storage, converter
        self.calls.append("open")
        self._flush()

    def create_topic(self, metadata):
        self.topics.append(metadata)
        self.calls.append("create_topic")
        self._flush()

    def write(self, topic, data, recv_timestamp, send_timestamp):
        if FakeWriter.fail_on_write is not None:
            raise FakeWriter.fail_on_write
        self.records.append((topic, data, recv_timestamp, send_timestamp))
        self.calls.append("write")

    def close(self):
        self.calls.append("close")
        self._flush()

    def _flush(self):
        self.path.write_bytes(pickle.dumps({"topics": self.topics, "records": self.records}))


class FakeReader:
    instances = []
    fail_after = None  # Raise OSError after this many read_next() calls.

    def __init__(self):
        self.closed, self.reads = False, 0
        FakeReader.instances.append(self)

    def open(self, storage, converter):
        files = sorted(Path(storage.uri).glob("*.mcap"))
        if not files:
            raise RuntimeError(f"No storage found at {storage.uri}")
        content = pickle.loads(files[0].read_bytes())
        self.topics, self.records = content["topics"], list(content["records"])

    def get_all_topics_and_types(self):
        return self.topics

    def has_next(self):
        return bool(self.records)

    def read_next(self):
        if FakeReader.fail_after is not None and self.reads >= FakeReader.fail_after:
            raise OSError("injected read failure")
        self.reads += 1
        topic, data, log_time, _ = self.records.pop(0)
        return topic, data, log_time

    def close(self):
        self.closed = True


def serialize_message(message):
    return pickle.dumps(message)


def deserialize_message(data, cls):
    message = pickle.loads(data)
    assert isinstance(message, cls), (type(message), cls)
    return message


def convert_rclcpp_qos_to_rclpy_qos(qos):
    return SimpleNamespace(durability=qos.durability, reliability=qos.reliability, depth=qos.depth)


def make_deps():
    FakeWriter.instances, FakeReader.instances = [], []
    FakeWriter.fail_on_write = FakeReader.fail_after = None
    return RosbagDeps(SequentialWriter=FakeWriter, SequentialReader=FakeReader, StorageOptions=StorageOptions,
                      ConverterOptions=ConverterOptions, TopicMetadata=TopicMetadata, QoS=QoS,
                      convert_rclcpp_qos_to_rclpy_qos=convert_rclcpp_qos_to_rclpy_qos,
                      serialize_message=serialize_message, deserialize_message=deserialize_message,
                      messages=dict(MESSAGES), report={"process_image": "kit.exe"})


FX = 752 * 24.0 / 33.6


def calibration(width=752, height=480, baseline=0.38):
    k = [[FX, 0.0, width / 2], [0.0, FX, height / 2], [0.0, 0.0, 1.0]]
    return {"resolution_wh": [width, height], "baseline_m": baseline, "K": {"left": k, "right": copy.deepcopy(k)},
            "distortion_coefficients": [0, 0, 0, 0, 0],
            "T_leftOptical_rightOptical": [[1, 0, 0, baseline], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}


def poses(index):
    left = [[0, 0, 1, 0.1 * index], [-1, 0, 0, 0.2], [0, -1, 0, 1.0], [0, 0, 0, 1]]
    return {"T_world_body": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            "T_world_optical": {"left": left, "right": left}, "T_world_changed_object": None}


def frames(width=752, height=480):
    import numpy as np

    rgba = np.zeros((height, width, 4), np.uint8)
    rgba[0, 0] = (200, 30, 90, 255)
    return {"left": rgba, "right": rgba.copy()}


def tamper(staging_dir, edit):
    """Rewrite the fake bag: ``edit(topics, records)`` returns the new (topics, records)."""
    path = sorted(Path(staging_dir).glob("*.mcap"))[0]
    content = pickle.loads(path.read_bytes())
    topics, records = edit(content["topics"], content["records"])
    path.write_bytes(pickle.dumps({"topics": topics, "records": records}))


def edit_messages(topic, change):
    """An ``edit`` for tamper() that applies change(message) to every message on ``topic``."""
    def edit(topics, records):
        result = []
        for name, data, recv, send in records:
            if name == topic:
                message = pickle.loads(data)
                change(message)
                data = pickle.dumps(message)
            result.append((name, data, recv, send))
        return topics, result
    return edit


TOPIC_COUNT = len(contract.TOPICS)
