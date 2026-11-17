"""Reopen a closed pass bag with rosbag2's reader and check it against the contract.

Runs in Kit's process after writer.close(), on mcap/.staging/<pass>/, outside any
measured benchmark row. Returns a list of problems; raises only for I/O errors.
Publish time is not readable here (read_next() returns the log time only).
See docs/designs/isaac-stereo-mcap.md ("Completeness check").
"""
from __future__ import annotations

from rov_sim.rosbag import contract

TOLERANCE = 1e-9


def _stamp(header):
    return header.stamp.sec * 10**9 + header.stamp.nanosec


def _close(values, expected, tolerance=TOLERANCE):
    values, expected = list(values), list(expected)
    return len(values) == len(expected) and all(abs(float(a) - float(b)) <= tolerance
                                                for a, b in zip(values, expected))


def _xyz(vector):
    return [vector.x, vector.y, vector.z]


def _xyzw(quaternion):
    return [quaternion.x, quaternion.y, quaternion.z, quaternion.w]


def _policy_name(value):
    name = getattr(value, "name", value)
    return str(name).lower()


class _Problems(list):
    """Collects problems, recording each kind once per topic so a bad bag stays readable."""

    def __init__(self):
        super().__init__()
        self._seen = set()

    def once(self, key, message):
        if key not in self._seen:
            self._seen.add(key)
            self.append(message)


def _check_topics(reader, problems):
    metadata = {topic.name: topic for topic in reader.get_all_topics_and_types()}
    expected = dict(contract.TOPICS)
    for name, ros_type in expected.items():
        if name not in metadata:
            problems.append(f"topic {name} is missing")
        elif metadata[name].type != ros_type:
            problems.append(f"topic {name} has type {metadata[name].type}, expected {ros_type}")
    for name in sorted(set(metadata) - set(expected)):
        problems.append(f"unexpected topic {name}")
    return metadata


def _check_tf_static_qos(metadata, deps, problems):
    topic = metadata.get(contract.TF_STATIC)
    if topic is None:
        return
    profiles = list(topic.offered_qos_profiles or ())
    if not profiles:
        problems.append(f"{contract.TF_STATIC} has no recorded QoS")
        return
    spec = contract.QOS[contract.TF_STATIC]
    for profile in profiles:
        qos = deps.convert_rclcpp_qos_to_rclpy_qos(profile)
        found = (_policy_name(qos.durability), _policy_name(qos.reliability))
        if found != (spec["durability"], spec["reliability"]):
            problems.append(f"{contract.TF_STATIC} QoS is durability={found[0]}, reliability={found[1]}; "
                            f"expected {spec['durability']}, {spec['reliability']}")


def _check_message(topic, message, log_time, calibration, expected_infos, expected_static, problems, poses, tfs):
    if topic in (contract.TF, contract.TF_STATIC):
        if len(message.transforms) != 1:
            problems.once((topic, "count"), f"{topic} at {log_time} has {len(message.transforms)} transforms, expected 1")
            return
        header = message.transforms[0].header
    else:
        header = message.header
    if _stamp(header) != log_time:
        problems.once((topic, "stamp"), f"{topic}: header stamp {_stamp(header)} differs from log time {log_time}")

    if topic in contract.IMAGE_TOPICS.values():
        side = "left" if topic == contract.LEFT_IMAGE else "right"
        width, height = (int(value) for value in calibration["resolution_wh"])
        found = (message.encoding, message.width, message.height, message.step, message.is_bigendian, len(message.data))
        wanted = (contract.IMAGE_ENCODING, width, height, 3 * width, 0, 3 * width * height)
        if found != wanted:
            problems.once((topic, "image"), f"{topic} is (encoding, width, height, step, is_bigendian, bytes) "
                                            f"{found}, expected {wanted}")
        if header.frame_id != contract.SIDE_FRAMES[side]:
            problems.once((topic, "frame"), f"{topic} frame_id {header.frame_id!r}, expected {contract.SIDE_FRAMES[side]!r}")
    elif topic in contract.INFO_TOPICS.values():
        fields = expected_infos[topic]
        if header.frame_id != fields["frame_id"]:
            problems.once((topic, "frame"), f"{topic} frame_id {header.frame_id!r}, expected {fields['frame_id']!r}")
        if (message.width, message.height, message.distortion_model) != (fields["width"], fields["height"], fields["distortion_model"]) \
                or not all(_close(getattr(message, key), fields[key]) for key in ("d", "k", "r", "p")):
            problems.once((topic, "values"), f"{topic} differs from stereo_calibration.json "
                                             f"(k={list(message.k)}, p={list(message.p)}; expected k={fields['k']}, p={fields['p']})")
    elif topic == contract.POSE:
        if header.frame_id != contract.MAP_FRAME:
            problems.once((topic, "frame"), f"{topic} frame_id {header.frame_id!r}, expected {contract.MAP_FRAME!r}")
        poses[log_time] = _xyz(message.pose.position) + _xyzw(message.pose.orientation)
    elif topic == contract.TF_STATIC:
        transform = message.transforms[0]
        if (header.frame_id, transform.child_frame_id) != (expected_static["frame_id"], expected_static["child_frame_id"]) \
                or not _close(_xyz(transform.transform.translation), expected_static["translation"]) \
                or not _close(_xyzw(transform.transform.rotation), expected_static["rotation_xyzw"]):
            problems.once((topic, "values"), f"{topic} at {log_time} is not {expected_static}")
    elif topic == contract.TF:
        transform = message.transforms[0]
        if (header.frame_id, transform.child_frame_id) != (contract.MAP_FRAME, contract.LEFT_FRAME):
            problems.once((topic, "frame"), f"{topic} is {header.frame_id!r} -> {transform.child_frame_id!r}, "
                                            f"expected {contract.MAP_FRAME!r} -> {contract.LEFT_FRAME!r}")
        tfs[log_time] = _xyz(transform.transform.translation) + _xyzw(transform.transform.rotation)


def check_pass(staging_dir, deps, calibration, completed_frames, fps):
    """Problems found in the closed bag at ``staging_dir``; an empty list means it may be committed."""
    problems = _Problems()
    expected_infos = {topic: contract.camera_info_fields(calibration, side) for side, topic in contract.INFO_TOPICS.items()}
    expected_static = contract.tf_static_fields(calibration)
    classes = {name: deps.messages[ros_type] for name, ros_type in contract.TOPICS}
    stamps_by_topic = {name: [] for name in contract.TOPIC_NAMES}
    poses, tfs = {}, {}
    reader = deps.SequentialReader()
    opened = False
    try:
        reader.open(deps.StorageOptions(uri=str(staging_dir), storage_id="mcap"), deps.ConverterOptions("cdr", "cdr"))
        opened = True
        metadata = _check_topics(reader, problems)
        _check_tf_static_qos(metadata, deps, problems)
        while reader.has_next():
            topic, data, log_time = reader.read_next()
            stamps_by_topic.setdefault(topic, []).append(log_time)
            if topic not in classes:
                continue
            message = deps.deserialize_message(data, classes[topic])
            _check_message(topic, message, log_time, calibration, expected_infos, expected_static, problems, poses, tfs)
    finally:
        # The Windows rename that follows fails while the reader holds the file.
        if opened:
            reader.close()
    problems.extend(contract.bundle_problems(stamps_by_topic, contract.expected_stamps(completed_frames, fps)))
    differing = [stamp for stamp in sorted(set(poses) & set(tfs)) if not _close(poses[stamp], tfs[stamp], 0.0)]
    if differing:
        problems.append(f"{contract.TF} differs from {contract.POSE} at {len(differing)} stamp(s), first {differing[0]}")
    return list(problems)
