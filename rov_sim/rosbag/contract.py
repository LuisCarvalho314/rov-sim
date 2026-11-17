"""Isaac stereo MCAP message contract, shared by the bag writer and its check.

Standard library only: no NumPy and no ROS imports, so CPU tests run anywhere.
See docs/designs/isaac-stereo-mcap.md ("Message contract").
"""
from __future__ import annotations

import math

FORMAT = "isaac-stereo-mcap"
FORMAT_VERSION = "1"

LEFT_FRAME = "left_camera_optical_frame"
RIGHT_FRAME = "right_camera_optical_frame"
MAP_FRAME = "map"

LEFT_IMAGE = "/stereo/left/image_raw"
RIGHT_IMAGE = "/stereo/right/image_raw"
LEFT_INFO = "/stereo/left/camera_info"
RIGHT_INFO = "/stereo/right/camera_info"
POSE = "/ground_truth/pose"
TF_STATIC = "/tf_static"
TF = "/tf"

IMAGE_TYPE = "sensor_msgs/msg/Image"
CAMERA_INFO_TYPE = "sensor_msgs/msg/CameraInfo"
POSE_TYPE = "geometry_msgs/msg/PoseStamped"
TF_TYPE = "tf2_msgs/msg/TFMessage"

# Write order within each frame; also the topic id order.
TOPICS = (
    (LEFT_IMAGE, IMAGE_TYPE),
    (RIGHT_IMAGE, IMAGE_TYPE),
    (LEFT_INFO, CAMERA_INFO_TYPE),
    (RIGHT_INFO, CAMERA_INFO_TYPE),
    (POSE, POSE_TYPE),
    (TF_STATIC, TF_TYPE),
    (TF, TF_TYPE),
)
TOPIC_NAMES = tuple(name for name, _ in TOPICS)
IMAGE_TOPICS = {"left": LEFT_IMAGE, "right": RIGHT_IMAGE}
INFO_TOPICS = {"left": LEFT_INFO, "right": RIGHT_INFO}
SIDE_FRAMES = {"left": LEFT_FRAME, "right": RIGHT_FRAME}

_VOLATILE = {"reliability": "reliable", "durability": "volatile", "depth": 10}
QOS = {name: dict(_VOLATILE) for name in TOPIC_NAMES}
QOS[TF_STATIC] = {"reliability": "reliable", "durability": "transient_local", "depth": 1}

# 2026-01-01T00:00:00Z: non-zero and a plausible date in ROS tools; the same for every pass.
EPOCH_NS = 1_767_225_600 * 10**9

IMAGE_ENCODING = "bgr8"
DISTORTION_MODEL = "plumb_bob"
_IDENTITY_3 = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _check_fps(fps):
    if isinstance(fps, bool) or not isinstance(fps, int):
        raise TypeError(f"fps must be a positive int, got {fps!r}")
    if fps <= 0:
        raise ValueError(f"fps must be a positive int, got {fps!r}")


def stamp_ns(index, fps):
    """Integer nanosecond stamp of frame ``index``: EPOCH_NS + index * 1e9 // fps."""
    _check_fps(fps)
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError(f"frame index must be a nonnegative int, got {index!r}")
    return EPOCH_NS + index * 10**9 // fps


def stamp_parts(stamp):
    """(sec, nanosec) for a builtin_interfaces/Time."""
    return divmod(stamp, 10**9)


def expected_stamps(completed_frames, fps):
    return [stamp_ns(index, fps) for index in range(completed_frames)]


def camera_info_fields(calibration, side):
    """CameraInfo fields from rov-sim's stereo_calibration.json.

    stereo_calibration.json stores cx = W/2, cy = H/2 (pixel-corner origin); ROS
    CameraInfo uses pixel centres, so both are shifted by -0.5.
    """
    if side not in SIDE_FRAMES:
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")
    width, height = (int(value) for value in calibration["resolution_wh"])
    if any(float(value) != 0.0 for value in calibration.get("distortion_coefficients", ())):
        raise ValueError("rov-sim calibration has nonzero distortion; the contract records D = 0")
    k = [[float(value) for value in row] for row in calibration["K"][side]]
    fx, skew, cx = k[0]
    fy, cy = k[1][1], k[1][2] - 0.5
    cx -= 0.5
    tx = -fx * float(calibration["baseline_m"]) if side == "right" else 0.0
    return {
        "frame_id": SIDE_FRAMES[side],
        "width": width,
        "height": height,
        "distortion_model": DISTORTION_MODEL,
        "d": [0.0] * 5,
        "k": [fx, skew, cx, 0.0, fy, cy, 0.0, 0.0, 1.0],
        "r": list(_IDENTITY_3),
        "p": [fx, skew, cx, tx, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0],
    }


def _matrix4(T):
    rows = [[float(value) for value in row] for row in T]
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        raise ValueError("expected a 4x4 homogeneous transform")
    return rows


def quaternion_xyzw(R):
    """Unit quaternion (x, y, z, w) of a 3x3 rotation by Shepperd's method, with w >= 0."""
    (r00, r01, r02), (r10, r11, r12), (r20, r21, r22) = R
    trace = r00 + r11 + r22
    largest = max(trace, r00, r11, r22)
    if largest == trace:
        w = 0.5 * math.sqrt(max(0.0, 1.0 + trace))
        x, y, z = (r21 - r12) / (4 * w), (r02 - r20) / (4 * w), (r10 - r01) / (4 * w)
    elif largest == r00:
        x = 0.5 * math.sqrt(max(0.0, 1.0 + r00 - r11 - r22))
        w, y, z = (r21 - r12) / (4 * x), (r01 + r10) / (4 * x), (r02 + r20) / (4 * x)
    elif largest == r11:
        y = 0.5 * math.sqrt(max(0.0, 1.0 - r00 + r11 - r22))
        w, x, z = (r02 - r20) / (4 * y), (r01 + r10) / (4 * y), (r12 + r21) / (4 * y)
    else:
        z = 0.5 * math.sqrt(max(0.0, 1.0 - r00 - r11 + r22))
        w, x, y = (r10 - r01) / (4 * z), (r02 + r20) / (4 * z), (r12 + r21) / (4 * z)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    sign = -1.0 if w < 0 else 1.0
    return [sign * x / norm, sign * y / norm, sign * z / norm, sign * w / norm]


def pose_fields(T):
    """(xyz, xyzw) of a 4x4 transform; for map -> left_camera_optical_frame."""
    rows = _matrix4(T)
    return [rows[0][3], rows[1][3], rows[2][3]], quaternion_xyzw([row[:3] for row in rows[:3]])


def tf_static_fields(calibration):
    """The single left -> right optical transform; the rig must be unrotated."""
    rows = _matrix4(calibration["T_leftOptical_rightOptical"])
    rotation = [value for row in rows[:3] for value in row[:3]]
    if any(abs(a - b) > 1e-9 for a, b in zip(rotation, _IDENTITY_3)):
        raise ValueError(f"T_leftOptical_rightOptical rotation is not the identity: {rows}")
    return {"frame_id": LEFT_FRAME, "child_frame_id": RIGHT_FRAME,
            "translation": [rows[0][3], rows[1][3], rows[2][3]],
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0]}


def rgba_to_bgr8(array):
    """RGBA (or RGB) -> contiguous BGR; accepts any NumPy-style indexable array."""
    result = array[..., [2, 1, 0]]
    flags = getattr(result, "flags", None)
    if flags is not None and not flags["C_CONTIGUOUS"]:
        result = result.copy(order="C")
    return result


def custom_data(commit, config_sha256, backend, pass_name, fps):
    """The bag's rosbag2 custom_data (metadata.yaml); every value is a string."""
    _check_fps(fps)
    return {
        "rov_sim.format": FORMAT,
        "rov_sim.format_version": FORMAT_VERSION,
        "rov_sim.writer_commit": str(commit),
        "rov_sim.config_sha256": str(config_sha256),
        "rov_sim.backend": str(backend),
        "rov_sim.pass": str(pass_name),
        "rov_sim.epoch_ns": str(EPOCH_NS),
        "rov_sim.fps": str(fps),
    }


def bundle_problems(stamps_by_topic, expected):
    """Missing, duplicate and unexpected stamps, and stamps lacking any contract topic.

    ``stamps_by_topic`` maps topic -> the log times read for it, in bag order.
    """
    expected_set = set(expected)
    problems = []
    seen = set()
    per_topic = {}
    for name in TOPIC_NAMES:
        stamps = list(stamps_by_topic.get(name, ()))
        unique = set(stamps)
        per_topic[name] = unique
        seen |= unique
        if len(unique) != len(stamps):
            problems.append(f"{name}: {len(stamps) - len(unique)} duplicate stamp(s)")
    for name in sorted(set(stamps_by_topic) - set(TOPIC_NAMES)):
        problems.append(f"unexpected topic {name}")
    missing = sorted(expected_set - seen)
    if missing:
        problems.append(f"{len(missing)} expected stamp(s) missing from every topic, first {missing[0]}")
    unexpected = sorted(seen - expected_set)
    if unexpected:
        problems.append(f"{len(unexpected)} unexpected stamp(s), first {unexpected[0]}")
    for stamp in sorted(seen & expected_set):
        lacking = [name for name in TOPIC_NAMES if stamp not in per_topic[name]]
        if lacking:
            problems.append(f"stamp {stamp} lacks {', '.join(lacking)}")
    return problems
