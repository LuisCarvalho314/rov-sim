"""Load rosbag2_py and rclpy from NVIDIA's Pixi ROS 2 workspace inside Kit's process.

Imported only with --record-mcap, after SimulationApp has started. It changes this
process only: ``<env>\\Library\\bin`` is appended to PATH (never first),
``<env>\\Library`` is prepended to AMENT_PREFIX_PATH, and ``<env>\\Lib\\site-packages``
is appended to the end of sys.path so Kit's NumPy keeps priority. It writes nothing.
See docs/designs/isaac-stereo-mcap.md ("Dependency bootstrap").
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ENV_VAR = "ROV_SIM_PIXI_ENV"
ROSBAG2_PY_VERSION = "0.26.10"
PROCESS_IMAGE = "kit.exe"
MCAP_PLUGIN = "rosbag2_storage_mcap.dll"
FIX = (f"Install NVIDIA's IsaacSim-ros_workspaces at tag IsaacSim-6.1.0 with `pixi install --locked` "
       f"in jazzy_ws, then set {ENV_VAR} to <workspace>\\jazzy_ws\\.pixi\\envs\\default "
       f"(docs/REPRODUCIBILITY.md).")

MESSAGE_TYPES = {
    "sensor_msgs/msg/Image": ("sensor_msgs.msg", "Image"),
    "sensor_msgs/msg/CameraInfo": ("sensor_msgs.msg", "CameraInfo"),
    "geometry_msgs/msg/PoseStamped": ("geometry_msgs.msg", "PoseStamped"),
    "geometry_msgs/msg/TransformStamped": ("geometry_msgs.msg", "TransformStamped"),
    "tf2_msgs/msg/TFMessage": ("tf2_msgs.msg", "TFMessage"),
    "builtin_interfaces/msg/Time": ("builtin_interfaces.msg", "Time"),
}


@dataclass(frozen=True)
class RosbagDeps:
    SequentialWriter: type
    SequentialReader: type
    StorageOptions: type
    ConverterOptions: type
    TopicMetadata: type
    QoS: type
    convert_rclcpp_qos_to_rclpy_qos: object
    serialize_message: object
    deserialize_message: object
    messages: dict = field(default_factory=dict)  # ROS type name -> message class
    report: dict = field(default_factory=dict)


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def _under(path, root):
    return path is not None and _norm(path).startswith(_norm(root).rstrip(os.sep) + os.sep)


def _fail(what, expected, found):
    raise RuntimeError(f"MCAP recording bootstrap: {what}. Expected {expected}; found {found}. {FIX}")


def process_image():
    """Full path of this process's executable (QueryFullProcessImageNameW on Windows)."""
    if os.name != "nt":
        return sys.executable
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    buffer = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buffer))
    if not kernel32.QueryFullProcessImageNameW(kernel32.GetCurrentProcess(), 0, buffer, ctypes.byref(size)):
        raise OSError(ctypes.get_last_error(), "QueryFullProcessImageNameW failed")
    return buffer.value


def package_version(site_packages, name):
    """Version of ``name`` from the distribution metadata inside ``site_packages`` only."""
    for distribution in importlib.metadata.distributions(name=name, path=[str(site_packages)]):
        return distribution.version
    return None


def _append_path_entry(variable, entry, *, first):
    current = os.environ.get(variable, "")
    parts = [part for part in current.split(os.pathsep) if part]
    if any(_norm(part) == _norm(entry) for part in parts):
        return
    parts = [str(entry), *parts] if first else [*parts, str(entry)]
    os.environ[variable] = os.pathsep.join(parts)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(*, get_process_image=process_image, get_package_version=package_version,
         import_module=importlib.import_module):
    """Apply the in-process Pixi overlay, import the ROS 2 bag API and verify it."""
    # 1. Find the environment.
    value = os.environ.get(ENV_VAR)
    if not value:
        _fail(f"{ENV_VAR} is not set", "the path of the Pixi environment", "nothing")
    env = Path(value)
    library_bin = env / "Library" / "bin"
    site_packages = env / "Lib" / "site-packages"
    for required in (library_bin / MCAP_PLUGIN, site_packages / "rosbag2_py"):
        if not required.exists():
            _fail("the Pixi environment is incomplete", f"{required}", "no such path")

    # 2. Record NumPy; refuse an rclpy/rosbag2_py loaded from anywhere else.
    numpy = sys.modules.get("numpy") or import_module("numpy")
    numpy_before = (numpy, numpy.__version__, numpy.__file__)
    for name in ("rclpy", "rosbag2_py"):
        module = sys.modules.get(name)
        if module is not None and not _under(getattr(module, "__file__", None), env):
            _fail(f"{name} is already loaded from outside the Pixi environment "
                  "(two ROS 2 Python builds in one process are untested; disable Isaac's ROS 2 bridge)",
                  f"{name} under {env}", getattr(module, "__file__", None))

    # 3. Apply the overlay, each change once.
    _append_path_entry("PATH", library_bin, first=False)
    _append_path_entry("AMENT_PREFIX_PATH", env / "Library", first=True)
    if not any(_norm(entry) == _norm(site_packages) for entry in sys.path):
        sys.path.append(str(site_packages))

    # 4. Import.
    try:
        rosbag2_py = import_module("rosbag2_py")
        storage = import_module("rosbag2_py._storage")
        rclpy = import_module("rclpy")
        serialization = import_module("rclpy.serialization")
        messages = {ros_type: getattr(import_module(module), name)
                    for ros_type, (module, name) in MESSAGE_TYPES.items()}
    except ImportError as error:
        _fail("rosbag2_py, rclpy or the message packages failed to import (a Python ABI or DLL mismatch)",
              f"CPython {sys.version_info.major}.{sys.version_info.minor} packages in {site_packages}",
              f"{type(error).__name__}: {error}")

    # 5. Check.
    current = sys.modules.get("numpy")
    if current is not numpy_before[0] or (getattr(current, "__version__", None), getattr(current, "__file__", None)) != numpy_before[1:]:
        _fail("NumPy changed while importing ROS 2 packages", f"Kit's NumPy {numpy_before[1]} at {numpy_before[2]}",
              f"{getattr(current, '__version__', None)} at {getattr(current, '__file__', None)}")
    for name, module in (("rosbag2_py", rosbag2_py), ("rclpy", rclpy)):
        if not _under(getattr(module, "__file__", None), env):
            _fail(f"{name} resolved outside the Pixi environment", f"{name} under {env}",
                  getattr(module, "__file__", None))
    version = get_package_version(site_packages, "rosbag2_py")
    if version != ROSBAG2_PY_VERSION:
        _fail("unexpected rosbag2_py version", ROSBAG2_PY_VERSION, version)
    image = get_process_image()
    if not str(image).lower().endswith(PROCESS_IMAGE):
        _fail("not running inside Kit", f"a process image ending in {PROCESS_IMAGE}", image)

    # 6. Return.
    lock = env.parents[2] / "pixi.lock" if len(env.parents) > 2 else None
    report = {"pixi_env": str(env), "numpy_version": numpy_before[1], "numpy_file": numpy_before[2],
              "rosbag2_py_file": rosbag2_py.__file__, "rosbag2_py_version": version,
              "rclpy_file": rclpy.__file__, "process_image": str(image),
              "pixi_lock_sha256": _sha256(lock) if lock is not None and lock.is_file() else None}
    return RosbagDeps(
        SequentialWriter=rosbag2_py.SequentialWriter, SequentialReader=rosbag2_py.SequentialReader,
        StorageOptions=rosbag2_py.StorageOptions, ConverterOptions=rosbag2_py.ConverterOptions,
        TopicMetadata=rosbag2_py.TopicMetadata, QoS=storage.QoS,
        convert_rclcpp_qos_to_rclpy_qos=rosbag2_py.convert_rclcpp_qos_to_rclpy_qos,
        serialize_message=serialization.serialize_message,
        deserialize_message=serialization.deserialize_message,
        messages=messages, report=report)
