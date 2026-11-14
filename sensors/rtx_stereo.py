"""Isaac Sim 6.1 experimental acquisition; OceanSim kernels remain unmodified.

Version-specific private access is confined here: SensorRuntime currently only
exposes cleanup through its destructor, and annotator nodes provide freshness.
"""
from __future__ import annotations

import json
import time
import copy
import warnings
from types import SimpleNamespace

import numpy as np
import omni.replicator.core as rep
import warp as wp
from pxr import UsdGeom

from sensors.stereo import CAMERA_PATHS, StereoCameras, tracy_zone, validate_geometry, world_matrix


def usd_intrinsics(stage, path, resolution):
    camera = UsdGeom.Camera(stage.GetPrimAtPath(path))
    width, height = resolution
    focal = camera.GetFocalLengthAttr().Get()
    return np.array([[width * focal / camera.GetHorizontalApertureAttr().Get(), 0, width / 2],
                     [0, height * focal / camera.GetVerticalApertureAttr().Get(), height / 2],
                     [0, 0, 1]], dtype=np.float32)


class _InputView:
    """Expose acquired arrays to the existing opt-in photometric diagnostics."""
    def __init__(self, owner, side, channel, annotator):
        self.owner, self.side, self.channel, self.annotator = owner, side, channel, annotator

    def get_data(self):
        if not self.owner.acquire():
            raise RuntimeError("RTX inputs not ready for diagnostic capture")
        return self.owner.inputs[self.side][self.channel]

    def get_node(self):
        return self.annotator.get_node()


class RtxStereoCameras(StereoCameras):
    def __init__(self, stage, cfg, directory, *, headless):
        self.stage, self.cfg = stage, cfg
        self.cameras, self.sensors, self.references = {}, [], []
        self.inputs, self.outputs, self._batches = {}, {}, {}
        self._closed = False
        self._acquired = False
        self._last_counts = None
        self._preview = {}
        self.transport = None
        self._gpu_pending = False
        self.tiled = cfg["stereo"]["backend"] == "tiled"
        (directory / "underwater_parameters.json").write_text(json.dumps(cfg["underwater"], indent=2))
        import omni.kit.app
        manager = omni.kit.app.get_app().get_extension_manager()
        manager.set_extension_enabled_immediate("isaacsim.sensors.experimental.rtx", True)
        if not manager.is_extension_enabled("isaacsim.sensors.experimental.rtx"):
            raise RuntimeError("Isaac Sim experimental RTX extension is unavailable; select --camera-backend legacy")
        from isaacsim.sensors.experimental.rtx import RtxCamera, CameraSensor, TiledCameraSensor
        from isaacsim.core.experimental.objects import Camera

        width, height = cfg["stereo"]["resolution"]
        resolution = (height, width)
        # Capture optics and transforms before wrappers can normalize USD xforms.
        before = {s: self._geometry(p) for s, p in CAMERA_PATHS.items()}
        try:
            if self.tiled:
                camera = Camera(list(CAMERA_PATHS.values()), reset_xform_op_properties=False)
                sensor = TiledCameraSensor(camera, resolution=resolution,
                                           annotators=["rgba", "distance_to_camera"])
                self.sensors.append(sensor)
                if list(sensor.camera.paths) != list(CAMERA_PATHS.values()):
                    raise RuntimeError(f"Unexpected tiled camera order: {sensor.camera.paths}")
            else:
                for path in CAMERA_PATHS.values():
                    camera = RtxCamera(path, tick_rate=0, reset_xform_op_properties=False)
                    self.sensors.append(CameraSensor(camera, resolution=resolution,
                                                      annotators=["rgba", "distance_to_camera"]))
            for index, (side, path) in enumerate(CAMERA_PATHS.items()):
                sensor = self.sensors[0 if self.tiled else index]
                product = str(sensor.render_product.GetPath())
                reference = next((a for p, a in self.references if p == product), None)
                if reference is None:
                    reference = rep.AnnotatorRegistry.get_annotator("ReferenceTime")
                    self.references.append((product, reference))
                    reference.attach(product)
                water = cfg["underwater"]
                cam = SimpleNamespace(
                    _id=0, _backscatter_value=wp.vec3f(*water["backscatter_value"]),
                    _atten_coeff=wp.vec3f(*water["atten_coeff"]),
                    _backscatter_coeff=wp.vec3f(*water["backscatter_coeff"]),
                    _max_range=water["max_range_m"], _depth_noise_sigma=water["depth_noise_sigma"],
                    _fabric_time_annotator=reference, _uw_frame=None, _degraded_depth_frame=None,
                    get_intrinsics_matrix=lambda p=path: usd_intrinsics(stage, p, cfg["stereo"]["resolution"]),
                    get_render_product_path=lambda p=product: p,
                )
                cam._rgba_annot = _InputView(self, side, 0, sensor._annotators["rgba"])
                cam._depth_annot = _InputView(self, side, 1, sensor._annotators["distance_to_camera"])
                self.cameras[side] = cam
                self.outputs[side] = (wp.empty((height, width, 4), dtype=wp.uint8, device="cuda"),
                                      wp.empty((height, width), dtype=wp.float32, device="cuda"))
                if cfg["stereo"]["preview"] and not headless:
                    import omni.ui as ui
                    window = ui.Window(f"ROV RTX {side}", width=width, height=height)
                    provider = ui.ByteImageProvider()
                    with window.frame:
                        ui.ImageWithProvider(provider)
                    self._preview[side] = (window, provider)
            for side, path in CAMERA_PATHS.items():
                after = self._geometry(path)
                if any(not np.allclose(a, b, atol=1e-6) for a, b in zip(before[side], after)):
                    raise RuntimeError(f"Experimental camera changed {side} geometry or optics")
            validate_geometry(stage, cfg["stereo"])
        except BaseException:
            self.close()
            raise

    def _geometry(self, path):
        cam = UsdGeom.Camera(self.stage.GetPrimAtPath(path))
        return (world_matrix(self.stage, path),
                [cam.GetFocalLengthAttr().Get(), cam.GetHorizontalApertureAttr().Get(),
                 cam.GetVerticalApertureAttr().Get(), cam.GetHorizontalApertureOffsetAttr().Get(),
                 cam.GetVerticalApertureOffsetAttr().Get()], list(cam.GetClippingRangeAttr().Get()))

    def after_render(self):
        # The application calls this only after the blocking, shared render step.
        self._acquired = False

    def before_render(self):
        """Finish GPU reads of borrowed buffers before the renderer reuses them."""
        if not self._gpu_pending:
            return 0.0
        start = time.perf_counter_ns()
        wp.synchronize_stream(wp.get_stream("cuda"))
        self._gpu_pending = False
        return (time.perf_counter_ns() - start) / 1e6

    def acquire(self):
        if self._acquired:
            return True
        width, height = self.cfg["stereo"]["resolution"]
        arrays = []
        for sensor in self.sensors:
            channels = []
            for name in ("rgba", "distance_to_camera"):
                if self.tiled:
                    key = name
                    if key not in self._batches:
                        dtype = wp.uint8 if name == "rgba" else wp.float32
                        self._batches[key] = wp.empty((2, height, width, 4 if name == "rgba" else 1),
                                                      dtype=dtype, device="cuda")
                    data, _ = sensor.get_data(name, out=self._batches[key])
                else:
                    data, _ = sensor.get_data(name)
                if data is None or data.size == 0:
                    return False
                if not isinstance(data, wp.array) or not data.device.is_cuda:
                    raise RuntimeError(f"{name} did not return a CUDA Warp array")
                expected = ((2,) if self.tiled else ()) + (height, width, 4 if name == "rgba" else 1)
                if data.shape != expected or data.dtype != (wp.uint8 if name == "rgba" else wp.float32):
                    raise RuntimeError(f"Invalid {name} layout: {data.shape}, {data.dtype}")
                channels.append(data)
            arrays.append(channels)
        # ReferenceTime and compute counts are CPU metadata, not image readbacks.
        refs = [a.get_data() for _, a in self.references]
        if len(refs) == 2 and refs[0] != refs[1]:
            raise RuntimeError(f"Unsynchronized stereo render products: {refs}")
        counts = tuple(a.get_node().get_compute_count() for sensor in self.sensors
                       for a in sensor._annotators.values())
        if self._last_counts is not None and any(a <= b for a, b in zip(counts, self._last_counts)):
            return False
        self._last_counts = counts
        for index, side in enumerate(CAMERA_PATHS):
            rgba, depth = arrays[0 if self.tiled else index]
            if self.tiled:
                rgba, depth = rgba[index], depth[index]
            # A reshape view removes the channel axis; it never converts radial range to Z.
            self.inputs[side] = (rgba, depth.reshape((height, width)))
        self._acquired = True
        if self.transport is None:
            # Once, during warmup or diagnostic setup: detect whether the API
            # hid a host upload. Do not infer zero-copy from the returned type.
            self.transport = []
            for sensor in self.sensors:
                self.transport.append({name: {
                    "source_type": type(a.get_data(device="cuda")).__name__,
                    "attach_device": "cuda", "do_array_copy": False,
                } for name, a in sensor._annotators.items()})
        return True

    def validate_equivalent_processing(self):
        """Replay identical inputs through actual production UW_Camera.render().

        Called only by target-free diagnostics; no render step or scene change.
        """
        from isaacsim.oceansim.sensors.UW_Camera import UW_Camera
        result = {}
        for side, cam in self.cameras.items():
            proxy = copy.copy(cam)
            proxy._id -= 1  # Replay exactly the same noise seed, including nonzero noise.
            proxy._viewport = proxy._writing = False
            proxy.get_resolution = lambda: tuple(self.cfg["stereo"]["resolution"])
            raw, clean = (a.numpy().copy() for a in self.inputs[side])
            UW_Camera.render(proxy)
            degraded = self.outputs[side][1].numpy()
            if not np.array_equal(proxy._uw_frame, cam._uw_frame):
                raise RuntimeError(f"{side}: RTX integration differs from UW_Camera RGB on identical inputs")
            if not np.array_equal(proxy._degraded_depth_frame, degraded, equal_nan=True):
                raise RuntimeError(f"{side}: RTX integration differs from UW_Camera degraded depth")
            if not (np.array_equal(raw, self.inputs[side][0].numpy()) and
                    np.array_equal(clean, self.inputs[side][1].numpy(), equal_nan=True)):
                raise RuntimeError(f"{side}: processing changed raw RGB or clean range")
            result[side] = {"production_render_rgb_bitwise_equal": True,
                            "production_render_degraded_depth_bitwise_equal": True,
                            "clean_inputs_unchanged": True}
        return result

    def infrastructure_report(self):
        return {"backend": self.cfg["stereo"]["backend"],
                "render_products": [str(s.render_product.GetPath()) for s in self.sensors],
                "resolution_hw": list(reversed(self.cfg["stereo"]["resolution"])),
                "held_time_pose_flush_before_capture": self.tiled,
                "transport": self.transport, "rgba": "uint8 RGBA, 0..255; no swizzle/normalization/flip",
                "depth": "float32 radial metres; trailing channel removed with a CUDA view",
                "processing": "Unmodified OceanSim UW_render and UW_depth_turbidity_attenuator",
                "readback": "RGB for normal output; degraded depth only when requested by geometric diagnostics",
                "synchronization": "Blocking shared Replicator render step; matching ReferenceTime; fresh RGB/depth node counts; Warp default CUDA stream; CPU numpy() waits; GPU-only stream fence before borrowed-buffer reuse; shutdown GPU drain"}

    def render_pair(self, timings=None, *, diagnostic_mode=None, tracy=False):
        from isaacsim.oceansim.utils.UWrenderer_utils import UW_render, UW_depth_turbidity_attenuator
        start = time.perf_counter_ns()
        with tracy_zone("ROV/RTXAcquisition", tracy):
            ready = self.acquire()
        acquired = time.perf_counter_ns()
        if timings is not None:
            timings["annotator_acquisition_ms"] += (acquired - start) / 1e6
        if not ready:
            return None
        height, width = reversed(self.cfg["stereo"]["resolution"])
        with tracy_zone("ROV/OceanSimGPU", tracy):
            for side, cam in self.cameras.items():
                rgba, depth = self.inputs[side]
                image, degraded = self.outputs[side]
                wp.launch(UW_render, dim=(height, width),
                          inputs=[rgba, depth, cam._backscatter_value, cam._atten_coeff,
                                  cam._backscatter_coeff], outputs=[image], device=rgba.device)
                wp.launch(UW_depth_turbidity_attenuator, dim=(height, width),
                          inputs=[rgba, depth, cam._max_range, cam._backscatter_value,
                                  cam._atten_coeff, cam._backscatter_coeff, cam._depth_noise_sigma,
                                  int(cam._id)], outputs=[degraded], device=depth.device)
                cam._id += 1
        submitted = time.perf_counter_ns()
        if timings is not None:
            timings["underwater_processing_ms"] += (submitted - acquired) / 1e6
        if diagnostic_mode == "no-readback":
            self._gpu_pending = True
            return {}
        frames = {}
        with tracy_zone("ROV/RTXCPUReadback", tracy):
            for side, (image, degraded) in self.outputs.items():
                cam = self.cameras[side]
                cam._uw_frame = image.numpy()
                # Degraded depth is only requested by geometric diagnostics.
                # Clean radial range remains in inputs and is never overwritten.
                frames[side] = cam._uw_frame
                if getattr(self, "download_degraded_depth", False):
                    cam._degraded_depth_frame = degraded.numpy()
                if side in self._preview:
                    self._preview[side][1].set_bytes_data(cam._uw_frame, (width, height))
        if timings is not None:
            timings["gpu_readback_ms"] += (time.perf_counter_ns() - submitted) / 1e6
        return frames

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            # Array lifetimes cover all pending work, including a no-readback run.
            wp.synchronize()
        finally:
            for product, reference in self.references:
                try:
                    reference.detach(product)
                except Exception as error:
                    warnings.warn(f"RTX reference cleanup: {error}")
            self.references.clear()
            for sensor in self.sensors:
                try:
                    sensor._invalidate_sensor()  # Installed 6.1 destructor's idempotent cleanup.
                except Exception as error:
                    warnings.warn(f"RTX sensor cleanup: {error}")
            self.sensors.clear()
            for window, provider in self._preview.values():
                window.destroy()
            self._preview.clear()
            self.cameras.clear()
            self.inputs.clear()
            self.outputs.clear()
            self._batches.clear()
