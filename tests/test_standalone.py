"""CPU checks for startup safety, deterministic experiments and paired output."""
from __future__ import annotations

import copy
import io
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from config import ROOT, find_oceansim_extension, load_config, resolve_path, validate_config
from experiments.change_detection import object_position, trajectory_pose
from recording import PoseRecorder, create_run_directory, write_png
import run
import startup


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_paths_are_repository_relative_even_from_another_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path.cwd()
            try:
                os.chdir(folder)
                self.assertEqual(resolve_path("outputs"), ROOT / "outputs")
                self.assertEqual(load_config(), self.cfg)
            finally:
                os.chdir(original)

    def test_invalid_calibration_and_geometry_fail_before_startup(self):
        changes = (("stereo", "baseline_m", 0), ("stereo", "resolution", [752, 480.5]),
                   ("water", "height_m", 4), ("water", "size_m", [100, 100]),
                   ("robot", "position_m", [99, 0, 1]), ("simulation", "fps", float("nan")),
                   ("underwater", "atten_coeff", [-1, 0, 0]))
        for section, key, value in changes:
            with self.subTest(section=section, key=key):
                cfg = copy.deepcopy(self.cfg)
                cfg[section][key] = value
                with self.assertRaises(ValueError):
                    validate_config(cfg)

    def test_unknown_and_unsupported_caustics_backend_combination(self):
        self.cfg["runtime"]["renderer"] = "PathTracing"
        with self.assertRaisesRegex(ValueError, "Photon caustics"):
            validate_config(self.cfg)

    def test_repeated_trajectory_frames_are_rejected(self):
        self.cfg["experiment"]["trajectory"][1]["frame"] = 0
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            validate_config(self.cfg)

    def test_extension_discovery_uses_existing_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            ext = Path(folder) / "extsUser/OceanSim"
            (ext / "config").mkdir(parents=True)
            (ext / "config/extension.toml").write_text('[package]\nversion="1.0.0"\n')
            with patch.dict(os.environ, {"ISAAC_PATH": folder, "OCEANSIM_EXT_PATH": ""}):
                self.assertEqual(find_oceansim_extension(self.cfg), ext)
            self.assertEqual(find_oceansim_extension(self.cfg, str(ext)), ext)


class StartupTests(unittest.TestCase):
    def test_help_and_validation_work_without_kit(self):
        for option in ("--help", "--validate-only"):
            result = subprocess.run([sys.executable, str(ROOT / "run.py"), option], cwd=tempfile.gettempdir(), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("omni.usd", sys.modules)
        self.assertNotIn("pxr", sys.modules)

    def test_windows_launch_overrides_vulkan_before_graphics_startup(self):
        cfg = load_config()
        with patch.object(startup.os, "name", "nt"):
            options = startup.launch_options(cfg, True)
        self.assertIn("--/app/vulkan=false", options["extra_args"])
        self.assertTrue(options["headless"])
        self.assertFalse(options["fast_shutdown"])
        self.assertEqual(options["renderer"], "RaytracedLighting")

    def test_app_closes_if_extension_startup_fails_and_restores_argv(self):
        events = []
        module = types.ModuleType("isaacsim")

        class FakeApp:
            def __init__(self, options, **kwargs):
                self.options = options
                events.append("start")
                self.test_args = sys.argv[:]

            def close(self):
                events.append("close")

        module.SimulationApp = FakeApp
        original = sys.argv
        with patch.dict(sys.modules, {"isaacsim": module}), \
             patch.object(run, "find_oceansim_extension", return_value=ROOT), \
             patch.object(startup, "launch_options", return_value={}), \
             patch.object(startup, "enable_oceansim", side_effect=RuntimeError("injected failure")):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                run.main(["--startup-only"])
        self.assertEqual(events, ["start", "close"])
        self.assertIs(sys.argv, original)

    def test_headless_and_experiment_cannot_run_unbounded(self):
        for args in (["--headless", "--frames", "0"], ["--experiment", "change_detection", "--frames", "0"]):
            with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(args)


class ExperimentTests(unittest.TestCase):
    def test_only_changed_object_position_differs(self):
        cfg = load_config()
        original = copy.deepcopy(cfg)
        self.assertEqual(object_position(cfg, "before"), [1.15, -0.65, 0.3])
        self.assertEqual(object_position(cfg, "after"), [1.65, -0.65, 0.3])
        self.assertEqual(cfg, original)

    def test_replayed_trajectory_is_identical_for_each_pass(self):
        cfg = load_config()
        points = cfg["experiment"]["trajectory"]
        before = [trajectory_pose(points, n) for n in range(60)]
        after = [trajectory_pose(points, n) for n in range(60)]
        self.assertEqual(before, after)
        self.assertEqual(before[0][0], points[0]["position_m"])
        self.assertEqual(before[-1][0], points[-1]["position_m"])
        self.assertEqual(trajectory_pose(points, 120)[0], points[-1]["position_m"])

    def test_heading_wrap_takes_short_rotation(self):
        points = [{"frame": n, "position_m": [n, 0, 1], "rotation_xyz_deg": [0, 0, yaw]}
                  for n, yaw in ((0, 170), (10, -170))]
        position, rotation = trajectory_pose(points, 5)
        self.assertEqual(position, [5, 0, 1])
        self.assertEqual(rotation, [0, 0, 180])


class RecordingTests(unittest.TestCase):
    def test_png_bytes_and_crc_roundtrip_without_an_image_dependency(self):
        class Row:
            def tobytes(self):
                return bytes([255, 0, 0, 255, 0, 255, 0, 255])

        class Frame:
            dtype, ndim, shape = "uint8", 3, (1, 2, 4)

            def __iter__(self):
                return iter([Row()])

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frame.png"
            write_png(path, Frame())
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            chunks = {}
            offset = 8
            while offset < len(data):
                length = struct.unpack(">I", data[offset:offset + 4])[0]
                tag, payload = data[offset + 4:offset + 8], data[offset + 8:offset + 8 + length]
                crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
                self.assertEqual(crc, zlib.crc32(tag + payload) & 0xFFFFFFFF)
                chunks[tag] = payload
                offset += length + 12
            self.assertEqual(struct.unpack(">IIBBBBB", chunks[b"IHDR"]), (2, 1, 8, 6, 0, 0, 0))
            self.assertEqual(zlib.decompress(chunks[b"IDAT"]), b"\x00" + Row().tobytes())

    def test_recording_preserves_existing_runs_and_pairs_pose_index(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = create_run_directory(folder), create_run_directory(folder)
            self.assertNotEqual(first, second)
            recorder = PoseRecorder(first / "before", images=False)
            try:
                recorder.record(3, 0.1, {}, {"T_world_body": [[1]]})
            finally:
                recorder.close()
            line = json.loads((first / "before/poses.jsonl").read_text())
            self.assertEqual((line["frame"], line["time_s"], line["images"]), (3, 0.1, {}))
            with self.assertRaises(FileExistsError):
                PoseRecorder(first / "before", images=False)


class CameraCleanupTests(unittest.TestCase):
    def test_camera_cleanup_releases_render_product_after_oceansim_close_fails(self):
        # Exercise the actual adapter without Kit. These API doubles isolate
        # failure recovery; they do not validate USD or GPU behavior.
        fake_pxr = types.ModuleType("pxr")
        fake_pxr.Gf = fake_pxr.Usd = fake_pxr.UsdGeom = object()
        robot = types.ModuleType("robots.bluerov")
        robot.VEHICLE_PATH = "/World/BlueROV"
        with patch.dict(sys.modules, {"pxr": fake_pxr, "robots.bluerov": robot}):
            spec = importlib.util.spec_from_file_location("_stereo_cleanup_check", ROOT / "sensors/stereo.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

        events = []

        class Annotator:
            def detach(self, *args):
                events.append("detach")

        class Camera:
            _rgba_annot = _depth_annot = _fabric_time_annotator = Annotator()
            _render_product_path = "/Render/Product"
            _acquisition_callback = _stage_open_callback = _timer_reset_callback = object()

            def close(self):
                events.append("close")
                raise RuntimeError("injected annotator failure")

            def destroy(self):
                events.append("destroy")

        cam = Camera()
        adapter = module.StereoCameras.__new__(module.StereoCameras)
        adapter.cameras, adapter._closed = {"left": cam}, False
        with self.assertWarnsRegex(UserWarning, "injected annotator failure"):
            adapter.close()
        adapter.close()
        self.assertEqual(events, ["close", "detach", "detach", "detach", "destroy"])
        self.assertIsNone(cam._acquisition_callback)
        self.assertIsNone(cam._stage_open_callback)
        self.assertIsNone(cam._timer_reset_callback)
        self.assertEqual(adapter.cameras, {})


if __name__ == "__main__":
    unittest.main()
