"""CPU checks of the in-process Pixi overlay and its failure messages (no ROS, no Kit)."""
from __future__ import annotations

import hashlib
import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy  # noqa: F401  Loaded before patch.dict(sys.modules), as in Kit.

from rov_sim.rosbag import deps

KIT = r"C:\isaacsim\kit\kit.exe"


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="rov pixi ")
        self.addCleanup(self.folder.cleanup)
        self.workspace = Path(self.folder.name) / "jazzy_ws"
        self.env = self.workspace / ".pixi" / "envs" / "default"
        self.bin = self.env / "Library" / "bin"
        self.site = self.env / "Lib" / "site-packages"
        self.bin.mkdir(parents=True)
        (self.bin / deps.MCAP_PLUGIN).write_bytes(b"")
        (self.site / "rosbag2_py").mkdir(parents=True)
        (self.workspace / "pixi.lock").write_bytes(b"lock\n")
        self.modules = self.fake_modules(self.site)
        for patcher in (patch.dict(os.environ, {deps.ENV_VAR: str(self.env), "PATH": r"C:\Windows",
                                                "AMENT_PREFIX_PATH": r"C:\isaacsim\jazzy"}),
                        patch.dict(sys.modules, self.modules),
                        patch.object(sys, "path", list(sys.path))):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def fake_modules(site):
        def module(name, **attributes):
            result = types.ModuleType(name)
            result.__file__ = str(site / name.replace(".", os.sep) / "__init__.py")
            result.__dict__.update(attributes)
            return result

        rosbag2_py = module("rosbag2_py", SequentialWriter=type("W", (), {}), SequentialReader=type("R", (), {}),
                            StorageOptions=object, ConverterOptions=object, TopicMetadata=object,
                            convert_rclcpp_qos_to_rclpy_qos=lambda q: q)
        result = {"rosbag2_py": rosbag2_py, "rosbag2_py._storage": module("rosbag2_py._storage", QoS=object),
                  "rclpy": module("rclpy"),
                  "rclpy.serialization": module("rclpy.serialization", serialize_message=bytes,
                                                deserialize_message=lambda data, cls: cls())}
        for ros_type, (name, attribute) in deps.MESSAGE_TYPES.items():
            result.setdefault(name, module(name))
            setattr(result[name], attribute, type(attribute, (), {"ros_type": ros_type}))
        return result

    def load(self, **overrides):
        options = {"get_process_image": lambda: KIT, "get_package_version": lambda site, name: deps.ROSBAG2_PY_VERSION}
        options.update(overrides)
        return deps.load(**options)

    def assertFails(self, pattern, **overrides):
        with self.assertRaisesRegex(RuntimeError, pattern) as caught:
            self.load(**overrides)
        message = str(caught.exception)
        self.assertIn("Expected", message)
        self.assertIn("found", message)
        self.assertIn(deps.ENV_VAR, message)
        return message

    def test_success_returns_api_and_report(self):
        loaded = self.load()
        self.assertIs(loaded.SequentialWriter, self.modules["rosbag2_py"].SequentialWriter)
        self.assertIs(loaded.QoS, object)
        self.assertEqual(set(loaded.messages), set(deps.MESSAGE_TYPES))
        report = loaded.report
        self.assertEqual(report["rosbag2_py_version"], "0.26.10")
        self.assertEqual(report["process_image"], KIT)
        self.assertEqual(report["pixi_lock_sha256"], hashlib.sha256(b"lock\n").hexdigest())
        self.assertEqual(report["numpy_version"], numpy.__version__)
        self.assertEqual(set(report), {"pixi_env", "numpy_version", "numpy_file", "rosbag2_py_file",
                                       "rosbag2_py_version", "rclpy_file", "process_image", "pixi_lock_sha256"})

    def test_missing_lock_is_recorded_as_null(self):
        (self.workspace / "pixi.lock").unlink()
        self.assertIsNone(self.load().report["pixi_lock_sha256"])

    def test_missing_environment_variable(self):
        del os.environ[deps.ENV_VAR]
        self.assertFails("is not set")

    def test_missing_dll(self):
        (self.bin / deps.MCAP_PLUGIN).unlink()
        self.assertIn(deps.MCAP_PLUGIN, self.assertFails("incomplete"))

    def test_missing_rosbag2_py_package(self):
        (self.site / "rosbag2_py").rmdir()
        self.assertIn("rosbag2_py", self.assertFails("incomplete"))

    def test_preloaded_foreign_rclpy_or_rosbag2_py(self):
        for name in ("rclpy", "rosbag2_py"):
            with self.subTest(name), patch.dict(sys.modules):
                foreign = types.ModuleType(name)
                foreign.__file__ = r"C:\isaacsim\exts\isaacsim.ros2.core\jazzy\rclpy\__init__.py"
                sys.modules[name] = foreign
                self.assertIn(foreign.__file__, self.assertFails("already loaded from outside"))

    def test_package_resolving_outside_environment(self):
        for name in ("rclpy", "rosbag2_py"):
            with self.subTest(name):
                real = importlib.import_module

                def import_module(module, name=name):
                    result = real(module)
                    if module == name:
                        result = types.ModuleType(name)
                        result.__dict__.update(self.modules[name].__dict__)
                        result.__file__ = r"C:\elsewhere\site-packages\%s\__init__.py" % name
                    return result

                self.assertFails(f"{name} resolved outside", import_module=import_module)

    def test_wrong_rosbag2_py_version(self):
        message = self.assertFails("unexpected rosbag2_py version",
                                   get_package_version=lambda site, name: "0.26.9")
        self.assertIn("0.26.10", message)
        self.assertIn("0.26.9", message)

    def test_wrong_process_image(self):
        message = self.assertFails("not running inside Kit", get_process_image=lambda: r"C:\Python312\python.exe")
        self.assertIn("python.exe", message)

    def test_import_failure_names_python_abi(self):
        def import_module(module):
            if module == "rosbag2_py":
                raise ImportError("DLL load failed while importing _storage")
            return importlib.import_module(module)

        self.assertIn("DLL load failed", self.assertFails("failed to import", import_module=import_module))

    def test_numpy_substitution_is_detected(self):
        real = importlib.import_module

        def import_module(module):
            if module == "rosbag2_py":
                shadow = types.ModuleType("numpy")
                shadow.__version__, shadow.__file__ = "2.5.1", str(self.site / "numpy" / "__init__.py")
                sys.modules["numpy"] = shadow
            return real(module)

        message = self.assertFails("NumPy changed", import_module=import_module)
        self.assertIn("2.5.1", message)

    def test_overlay_positions_and_idempotence(self):
        self.load()
        self.assertEqual(os.path.normcase(sys.path[-1]), os.path.normcase(str(self.site)))
        path = os.environ["PATH"].split(os.pathsep)
        self.assertEqual(path, [r"C:\Windows", str(self.bin)])
        ament = os.environ["AMENT_PREFIX_PATH"].split(os.pathsep)
        self.assertEqual(ament, [str(self.env / "Library"), r"C:\isaacsim\jazzy"])
        before = (list(sys.path), os.environ["PATH"], os.environ["AMENT_PREFIX_PATH"])
        self.load()
        self.assertEqual((list(sys.path), os.environ["PATH"], os.environ["AMENT_PREFIX_PATH"]), before)

    def test_existing_entries_with_other_case_or_trailing_separator_are_not_duplicated(self):
        bin_variant = str(self.bin).upper() + os.sep
        library_variant = str(self.env / "Library").lower() + os.sep
        site_variant = str(self.site).upper() + os.sep
        os.environ["PATH"] = os.pathsep.join([bin_variant, r"C:\Windows"])
        os.environ["AMENT_PREFIX_PATH"] = os.pathsep.join([r"C:\isaacsim\jazzy", library_variant])
        sys.path.insert(0, site_variant)
        count = len(sys.path)
        self.load()
        self.assertEqual(os.environ["PATH"], os.pathsep.join([bin_variant, r"C:\Windows"]))
        self.assertEqual(os.environ["AMENT_PREFIX_PATH"], os.pathsep.join([r"C:\isaacsim\jazzy", library_variant]))
        self.assertEqual(len(sys.path), count)


if __name__ == "__main__":
    unittest.main()
