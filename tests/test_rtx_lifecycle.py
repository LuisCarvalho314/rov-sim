"""CPU failure-path and borrowed-buffer lifetime tests; no Kit imports."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class RtxLifecycleTests(unittest.TestCase):
    def setUp(self):
        stereo = types.ModuleType("sensors.stereo")
        stereo.CAMERA_PATHS = {"left": "/Left", "right": "/Right"}
        stereo.StereoCameras = object
        stereo.tracy_zone = stereo.validate_geometry = stereo.world_matrix = MagicMock()
        self.wp = types.ModuleType("warp")
        self.wp.synchronize_stream = MagicMock()
        self.wp.get_stream = MagicMock(return_value="stream0")
        self.wp.synchronize = MagicMock()
        modules = {"sensors.stereo": stereo, "warp": self.wp,
                   "omni": types.ModuleType("omni"),
                   "omni.replicator": types.ModuleType("omni.replicator"),
                   "omni.replicator.core": types.ModuleType("omni.replicator.core"),
                   "pxr": types.SimpleNamespace(UsdGeom=MagicMock())}
        spec = importlib.util.spec_from_file_location("rtx_lifecycle_test_subject",
                    Path(__file__).resolve().parents[1] / "sensors/rtx_stereo.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        self.camera = object.__new__(module.RtxStereoCameras)

    def test_fence_only_when_gpu_work_is_pending_and_before_buffer_reuse(self):
        self.camera._gpu_pending = False
        self.assertEqual(self.camera.before_render(), 0)
        self.wp.synchronize_stream.assert_not_called()
        self.camera._gpu_pending = True
        self.assertGreaterEqual(self.camera.before_render(), 0)
        self.wp.synchronize_stream.assert_called_once_with("stream0")
        self.assertFalse(self.camera._gpu_pending)
        self.camera.before_render()
        self.wp.synchronize_stream.assert_called_once()

    def test_failed_fence_does_not_mark_buffers_safe_to_reuse(self):
        self.camera._gpu_pending = True
        self.wp.synchronize_stream.side_effect = RuntimeError("CUDA failure")
        with self.assertRaisesRegex(RuntimeError, "CUDA failure"):
            self.camera.before_render()
        self.assertTrue(self.camera._gpu_pending)

    def test_partial_cleanup_continues_and_is_idempotent(self):
        self.camera._closed = False
        reference, sensor, window = MagicMock(), MagicMock(), MagicMock()
        reference.detach.side_effect = RuntimeError("detach failed")
        self.camera.references = [("/Render/Test", reference)]
        self.camera.sensors = [sensor]
        self.camera._preview = {"left": (window, MagicMock())}
        self.camera.cameras = self.camera.inputs = self.camera.outputs = self.camera._batches = {}
        with self.assertWarnsRegex(UserWarning, "detach failed"):
            self.camera.close()
        sensor._invalidate_sensor.assert_called_once()
        window.destroy.assert_called_once()
        self.wp.synchronize.assert_called_once()
        self.camera.close()
        self.wp.synchronize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
