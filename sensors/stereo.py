"""Vehicle-mounted USD stereo calibration and OceanSim UW_Camera lifecycle."""
from __future__ import annotations

import json
import time
import warnings
from contextlib import contextmanager

import numpy as np
from pxr import Gf, Usd, UsdGeom

from robots.bluerov import VEHICLE_PATH

RIG_PATH = VEHICLE_PATH + "/StereoRig"
CAMERA_PATHS = {side: RIG_PATH + "/" + side.title() for side in ("left", "right")}


@contextmanager
def tracy_zone(name, enabled):
    if enabled:
        import carb.profiler
        carb.profiler.begin(1, name)
    try:
        yield
    finally:
        if enabled:
            carb.profiler.end(1)


def build_stereo_rig(stage, cfg):
    if stage.GetPrimAtPath(RIG_PATH):
        raise RuntimeError("Stereo rig already exists")
    rig = UsdGeom.Xform.Define(stage, RIG_PATH)
    api = UsdGeom.XformCommonAPI(rig)
    api.SetTranslate(Gf.Vec3d(*cfg["mount"]["position_m"]))
    api.SetRotate(Gf.Vec3f(*cfg["mount"]["rotation_xyz_deg"]))
    width, height = cfg["resolution"]
    for side, sign in (("left", -1), ("right", 1)):
        cam = UsdGeom.Camera.Define(stage, CAMERA_PATHS[side])
        cam.CreateProjectionAttr(UsdGeom.Tokens.perspective)
        cam.CreateFocalLengthAttr(cfg["focal_length_mm"])
        cam.CreateHorizontalApertureAttr(cfg["horizontal_aperture_mm"])
        cam.CreateVerticalApertureAttr(cfg["horizontal_aperture_mm"] * height / width)
        cam.CreateHorizontalApertureOffsetAttr(0.0)
        cam.CreateVerticalApertureOffsetAttr(0.0)
        cam.CreateClippingRangeAttr(Gf.Vec2f(*cfg["clipping_range_m"]))
        UsdGeom.XformCommonAPI(cam).SetTranslate(Gf.Vec3d(sign * cfg["baseline_m"] / 2, 0, 0))


def world_matrix(stage, path, *, optical=False):
    """Column-vector T_world_frame; optical = X right, Y down, Z forward."""
    row_matrix = UsdGeom.Xformable(stage.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    matrix = np.array(row_matrix, dtype=float).T
    if optical:
        matrix = matrix @ np.diag([1.0, -1.0, -1.0, 1.0])
    return matrix


def validate_geometry(stage, cfg):
    left, right = (world_matrix(stage, CAMERA_PATHS[s]) for s in ("left", "right"))
    relative = np.linalg.inv(left) @ right
    expected = np.eye(4)
    expected[0, 3] = cfg["baseline_m"]
    if not np.allclose(relative, expected, atol=1e-6):
        raise RuntimeError(f"Stereo axes/baseline are incorrect: T_leftUSD_rightUSD={relative}")
    # Sensor extrinsics must stay fixed in the body frame, regardless of pose.
    body = world_matrix(stage, VEHICLE_PATH)
    return {s: (np.linalg.inv(body) @ world_matrix(stage, p, optical=True)).tolist()
            for s, p in CAMERA_PATHS.items()}


class StereoCameras:
    """Small adapter around the installed OceanSim 1.0.0 camera API."""

    def __init__(self, stage, cfg, directory, *, headless):
        self.stage, self.cfg = stage, cfg
        self.cameras = {}
        self._closed = False
        # Named YAML fields avoid the inconsistent UW_param slice ordering in
        # this OceanSim version's docstring vs implementation. JSON is YAML.
        water_file = directory / "underwater_parameters.json"
        water_file.write_text(json.dumps(cfg["underwater"], indent=2), encoding="utf-8")
        from isaacsim.oceansim.sensors.UW_Camera import UW_Camera

        try:
            for side, path in CAMERA_PATHS.items():
                cam = UW_Camera(prim_path=path, name=f"ROV_UW_{side}", resolution=tuple(cfg["stereo"]["resolution"]))
                self.cameras[side] = cam  # Own partially initialized resources too.
                cam.initialize(
                    UW_yaml_path=str(water_file),
                    depth_noise_sigma=cfg["underwater"]["depth_noise_sigma"],
                    max_range=cfg["underwater"]["max_range_m"],
                    viewport=cfg["stereo"]["preview"] and not headless,
                )
            validate_geometry(stage, cfg["stereo"])
        except BaseException:
            self.close()
            raise

    def calibration(self):
        extrinsics = validate_geometry(self.stage, self.cfg["stereo"])
        matrices = {side: np.asarray(cam.get_intrinsics_matrix()).tolist() for side, cam in self.cameras.items()}
        if not np.allclose(matrices["left"], matrices["right"], atol=1e-5):
            raise RuntimeError("Left/right intrinsics differ")
        c = self.cfg["stereo"]
        width, height = c["resolution"]
        fx = width * c["focal_length_mm"] / c["horizontal_aperture_mm"]
        expected = [[fx, 0, width / 2], [0, fx, height / 2], [0, 0, 1]]
        if not np.allclose(matrices["left"], expected, atol=1e-4):
            raise RuntimeError(f"Initialized camera intrinsics differ from configuration: {matrices}")
        return {
            "resolution_wh": c["resolution"], "baseline_m": c["baseline_m"],
            "K": matrices, "distortion_model": "pinhole", "distortion_coefficients": [0, 0, 0, 0, 0],
            "T_body_optical": extrinsics,
            "T_leftOptical_rightOptical": [[1, 0, 0, c["baseline_m"]], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            "frames": {"world_body": "+X forward, +Y left, +Z up", "usd_camera": "+X right, +Y up, -Z forward", "optical": "+X right, +Y down, +Z forward"},
            "matrix_convention": "Column vectors: p_parent = T_parent_child @ p_child; translations in metres",
            "camera_paths": CAMERA_PATHS,
            "formation": "OceanSim depth-based attenuation/backscatter; no refractive stereo calibration or housing distortion model",
        }

    def render_pair(self, timings=None, *, diagnostic_mode=None, tracy=False):
        # OceanSim 1.0.0 exposes its processed image as _uw_frame. Keep all
        # version-specific access here. Check both annotators before invoking
        # its GPU kernel; an RGB frame alone does not guarantee depth readiness.
        start = time.perf_counter_ns() if timings is not None else None
        width, height = self.cfg["stereo"]["resolution"]
        with tracy_zone("ROV/StereoAnnotatorReadiness", tracy):
            for cam in self.cameras.values():
                if cam._rgba_annot.get_data().size == 0 or cam._depth_annot.get_data().size == 0:
                    if timings is not None:
                        timings["annotator_acquisition_ms"] += (time.perf_counter_ns() - start) / 1e6
                    return None
        if timings is not None:
            timings["annotator_acquisition_ms"] += (time.perf_counter_ns() - start) / 1e6
            start = time.perf_counter_ns()
        frames = {}
        for side, cam in self.cameras.items():
            if diagnostic_mode:
                frame = self._render_camera_diagnostic(cam, side, diagnostic_mode, timings, tracy)
                if diagnostic_mode == "no-readback":
                    if frame is None:
                        return None
                    continue
            else:
                cam.render()
                frame = cam._uw_frame
            if frame is None or frame.shape[:2] != (height, width):
                if timings is not None:
                    timings["processing_readback_combined_ms"] += (time.perf_counter_ns() - start) / 1e6
                return None
            frames[side] = frame.copy() if not diagnostic_mode else frame
        if timings is not None:
            timings["processing_readback_combined_ms"] += (time.perf_counter_ns() - start) / 1e6
        return frames

    @staticmethod
    def _render_camera_diagnostic(cam, side, mode, timings, tracy):
        """OceanSim 1.0.0 render stages, split only for opt-in profiling."""
        if cam._viewport or cam._writing:
            raise RuntimeError("Diagnostic OceanSim path requires headless capture without camera writing")
        import warp as wp
        from isaacsim.oceansim.utils.UWrenderer_utils import UW_depth_turbidity_attenuator, UW_render

        with tracy_zone(f"ROV/{side}/OceanSimAnnotatorFetch", tracy):
            raw_rgba = cam._rgba_annot.get_data()
            depth = cam._depth_annot.get_data()
        if raw_rgba.size == 0 or depth.size == 0:
            return None
        processing_start = time.perf_counter_ns()
        with tracy_zone(f"ROV/{side}/OceanSimRGB", tracy):
            uw_image = wp.zeros_like(raw_rgba)
            wp.launch(dim=np.flip(cam.get_resolution()), kernel=UW_render,
                      inputs=[raw_rgba, depth, cam._backscatter_value, cam._atten_coeff,
                              cam._backscatter_coeff], outputs=[uw_image])
        with tracy_zone(f"ROV/{side}/OceanSimDepth", tracy):
            degraded_depth = wp.zeros_like(depth)
            wp.launch(dim=np.flip(cam.get_resolution()), kernel=UW_depth_turbidity_attenuator,
                      inputs=[raw_rgba, depth, cam._max_range, cam._backscatter_value,
                              cam._atten_coeff, cam._backscatter_coeff, cam._depth_noise_sigma,
                              int(cam._id)], outputs=[degraded_depth])
        readback_start = time.perf_counter_ns()
        if timings is not None:
            timings["underwater_processing_ms"] += (readback_start - processing_start) / 1e6
        if mode == "no-readback":
            cam._profile_gpu_arrays = (uw_image, degraded_depth)
            cam._id += 1
            return True
        with tracy_zone(f"ROV/{side}/CPUReadback", tracy):
            cam._uw_frame = uw_image.numpy()
            cam._degraded_depth_frame = np.ascontiguousarray(degraded_depth.numpy(), dtype=np.float32)
            frame = cam._uw_frame.copy()
        if timings is not None:
            timings["gpu_readback_ms"] += (time.perf_counter_ns() - readback_start) / 1e6
        cam._id += 1
        return frame

    def close(self):
        if self._closed:
            return
        self._closed = True
        cameras = tuple(self.cameras.items())
        try:
            # OceanSim.close() also calls AnnotatorCache.clear with an annotator
            # object, although Replicator's cache expects an integer ID. Its
            # cache is global, so detach each camera explicitly instead.
            for side, cam in cameras:
                for name in ("_rgba_annot", "_depth_annot", "_fabric_time_annotator"):
                    annotator = getattr(cam, name, None)
                    product = getattr(cam, "_render_product_path", None)
                    if annotator is None or not product:
                        continue
                    try:
                        if product in (getattr(annotator, "_render_products", None) or ()):
                            annotator.detach(product)
                    except Exception as error:
                        warnings.warn(f"{side} {name} cleanup: {error}")
                if getattr(cam, "_viewport", False) and hasattr(cam, "wrapped_ui_elements"):
                    try:
                        cam.ui_destroy()
                    except Exception as error:
                        warnings.warn(f"{side} OceanSim viewport cleanup: {error}")
                # Isaac Camera.initialize() also attaches its own RGB annotator.
                # Detach these on both products before either product is removed.
                for name in tuple(getattr(cam, "_custom_annotators", ())):
                    try:
                        cam.detach_annotator(name)
                    except Exception as error:
                        warnings.warn(f"{side} Isaac {name} cleanup: {error}")
            # Camera.destroy() owns its inherited RGB annotator and render product.
            for side, cam in cameras:
                try:
                    cam.destroy()
                except Exception as error:
                    warnings.warn(f"{side} render product cleanup: {error}")
                for name in ("_acquisition_callback", "_stage_open_callback", "_timer_reset_callback"):
                    if hasattr(cam, name):
                        setattr(cam, name, None)
        finally:
            self.cameras.clear()
