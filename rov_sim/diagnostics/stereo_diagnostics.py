"""Opt-in checks around the existing application/recorder, never a second simulator.

Geometry and equation checks adapted from the already validated OceanSim
 diagnostics/rov_stereo_smoke.py; all simulation components import from this repo.
"""
from pathlib import Path
import numpy as np
import carb.settings
import omni.timeline
from pxr import Gf, Sdf, UsdGeom, UsdShade, UsdLux
from rov_sim.recording import write_json, write_png
from rov_sim.sensors.stereo import CAMERA_PATHS, world_matrix, validate_geometry

CFG = {"target_center_m": [1.35, -0.30, 1.65],
       "target_size_m": [0.02, 0.32, 0.24],
       "pixel_tolerance": 1.25, "depth_tolerance_m": 0.025}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (np.ndarray, list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def reference(camera):
    return jsonable(camera._fabric_time_annotator.get_data())


def compute_counts(cameras):
    return {s: {"rgb": c._rgba_annot.get_node().get_compute_count(),
                "depth": c._depth_annot.get_node().get_compute_count()}
            for s, c in cameras.items()}


def add_target(stage, exposure_scale=1.0):
    """One emissive magenta fiducial, in addition to the original equipment."""
    cube = UsdGeom.Cube.Define(stage, "/World/DiagnosticTarget")
    cube.CreateSizeAttr(1)
    cube.AddTranslateOp().Set(Gf.Vec3d(*CFG["target_center_m"]))
    cube.AddScaleOp().Set(Gf.Vec3f(*CFG["target_size_m"]))
    mat = UsdShade.Material.Define(stage, "/World/Looks/DiagnosticTarget")
    shader = UsdShade.Shader.Define(stage, str(mat.GetPath()) + "/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.8*exposure_scale, 0, 0.8*exposure_scale))
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(2*exposure_scale, 0, 2*exposure_scale))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(mat)


def projection(stage, path, point, k):
    optical = np.linalg.inv(world_matrix(stage, path, optical=True)) @ np.r_[point, 1]
    pixel = k @ optical[:3]
    return pixel[:2] / pixel[2], optical[:3]


def largest_component(mask):
    """Isolate the solid fiducial from smaller water/specular reflections."""
    pending = mask.copy()
    largest = []
    for y, x in np.argwhere(mask):
        if not pending[y, x]:
            continue
        stack, component = [(int(y), int(x))], []
        pending[y, x] = False
        while stack:
            cy, cx = stack.pop()
            component.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and pending[ny, nx]:
                    pending[ny, nx] = False
                    stack.append((ny, nx))
        if len(component) > len(largest):
            largest = component
    return np.array(largest).T if largest else np.empty((2, 0), dtype=int)


def check_geometry(stage, camera, raw, depth, k, side):
    """Measure target in RGB; check metric ranges and an independent tank wall."""
    center = np.array(CFG["target_center_m"], dtype=float)
    center[0] -= CFG["target_size_m"][0] / 2  # Visible front at x=1.34.
    path = CAMERA_PATHS[side]
    predicted, optical = projection(stage, path, center, k)
    rgb = raw[..., :3].astype(float)
    mask = (rgb[..., 0] > 150) & (rgb[..., 2] > 150)
    mask &= (rgb[..., 0] > rgb[..., 1] + 55) & (rgb[..., 2] > rgb[..., 1] + 55)
    yy, xx = largest_component(mask)
    require(len(xx) > 100, f"{side}: fiducial not visible ({len(xx)} pixels)")
    measured = np.array([xx.mean() + 0.5, yy.mean() + 0.5])
    # When yawed, projected rectangle centre differs slightly from area centroid.
    require(np.max(np.abs(measured - predicted)) < CFG["pixel_tolerance"],
            f"{side}: stale pose/image or wrong orientation: measured {measured}, predicted {predicted}")
    u, v = np.floor(predicted).astype(int)
    ray = np.array([(u + 0.5 - k[0, 2]) / k[0, 0],
                    (v + 0.5 - k[1, 2]) / k[1, 1], 1.0])
    transform = world_matrix(stage, path, optical=True)
    direction = transform[:3, :3] @ ray
    z_expected = (center[0] - transform[0, 3]) / direction[0]
    radial_expected = z_expected * np.linalg.norm(ray)
    radial_measured = float(depth[v, u])
    z_measured = radial_measured / np.linalg.norm(ray)
    require(abs(radial_measured - radial_expected) < CFG["depth_tolerance_m"],
            f"{side}: target range {radial_measured} != {radial_expected}")
    # Ray into bare east wall (x=3.9), away from pipes, panel and target.
    wall_point = [3.9, -1.1, 1.9]
    wall_pixel, _ = projection(stage, path, wall_point, k)
    wu, wv = np.floor(wall_pixel).astype(int)
    wall_ray = np.array([(wu + 0.5 - k[0, 2]) / k[0, 0],
                         (wv + 0.5 - k[1, 2]) / k[1, 1], 1.0])
    wall_direction = transform[:3, :3] @ wall_ray
    wall_range = (3.9 - transform[0, 3]) / wall_direction[0] * np.linalg.norm(wall_ray)
    require(abs(float(depth[wv, wu]) - wall_range) < CFG["depth_tolerance_m"],
            f"{side}: tank wall range disagrees with pose")
    return {"predicted_uv": predicted.tolist(), "measured_uv": measured.tolist(),
            "target_world_front_center_m": center.tolist(), "target_optical_xyz_m": optical.tolist(),
            "range_expected_m": float(radial_expected), "range_measured_m": radial_measured,
            "optical_z_measured_m": float(z_measured), "optical_z_ray_expected_m": float(z_expected),
            "wall_range_expected_m": float(wall_range), "wall_range_measured_m": float(depth[wv, wu]),
            "fiducial_pixels": len(xx)}


def check_underwater(camera, raw, depth):
    processed = camera._uw_frame
    degraded = camera._degraded_depth_frame
    require(processed.shape == raw.shape and processed.dtype == np.uint8, "Invalid processed RGBA")
    require(degraded.shape == depth.shape and degraded.dtype == np.float32, "Invalid degraded depth")
    require(np.isfinite(processed).all() and np.isfinite(degraded).all(), "Nonfinite processed output")
    b = np.array(list(camera._backscatter_value))
    a = np.array(list(camera._atten_coeff))
    c = np.array(list(camera._backscatter_coeff))
    direct = raw[..., :3].astype(float) * np.exp(-depth[..., None] * a)
    expected = np.clip(direct + 255 * b * (1 - np.exp(-depth[..., None] * c)), 0, 255)
    error = np.abs(processed[..., :3].astype(float) - expected)
    require(error.max() <= 1.01, f"Underwater RGB equation error: {error.max()}")
    retained = (direct.mean(2) / 255 > 0.25) & np.isfinite(depth)
    require(np.all(degraded[~retained] == 0), "Depth rejection mismatch")
    # Original configuration has zero depth noise.
    require(np.allclose(degraded[retained], depth[retained], atol=2e-6), "Clean/degraded depth mismatch")
    require(np.array_equal(processed[..., 3], raw[..., 3]), "Alpha changed")
    return {"equation_max_error_8bit": float(error.max()),
            "mean_rgb_change": float(np.abs(processed[..., :3].astype(float) - raw[..., :3]).mean()),
            "retained_depth_pixels": int(retained.sum()), "raw_dtype": str(raw.dtype),
            "depth_dtype": str(depth.dtype), "channel_order": "RGBA", "depth_convention": "radial metres"}


class StereoDiagnostics:
    def __init__(self, stage, cfg, directory):
        self.stage, self.cfg = stage, cfg
        self.directory = Path(directory) / "diagnostics"
        self.directory.mkdir()
        self.rows = []
        self.extrinsics = validate_geometry(stage, cfg["stereo"])
        self.products = None
        self.overview_product = self.overview_annot = None
        # Keep this geometric marker in the same display range when exposure
        # changes. It is absent from all target-free photometric evidence.
        exposure = cfg["rtx"]["settings"]
        scale = (100.0/exposure.get("/rtx/post/tonemap/filmIso",100.0)
                 * .02/exposure.get("/rtx/post/tonemap/exposureTime",.02)
                 * (exposure.get("/rtx/post/tonemap/fNumber",5.0)/5.0)**2)
        self.target_exposure_scale = scale
        add_target(stage, scale)
        write_json(self.directory / "summary.json", {"status": "initializing", "target": CFG})

    def before_render(self, stereo):
        self.counts_before = compute_counts(stereo.cameras)

    def capture_inputs(self, stereo):
        self.counts_after = compute_counts(stereo.cameras)
        self.refs = {s: reference(c) for s, c in stereo.cameras.items()}
        require(self.refs["left"] == self.refs["right"], f"Unsynchronized products: {self.refs}")
        require(all(self.counts_after[s][a] > self.counts_before[s][a]
                    for s in stereo.cameras for a in ("rgb", "depth")), "Stale RGB/depth annotators")
        self.inputs = {}
        for side, cam in stereo.cameras.items():
            rgba, depth = cam._rgba_annot.get_data(), cam._depth_annot.get_data()
            require(rgba.device.is_cuda and depth.device.is_cuda, "Expected CUDA inputs")
            self.inputs[side] = (rgba, depth, rgba.numpy().copy(), depth.numpy().copy())

    def validate_pair(self, stereo, pair, pass_name, index, time_s, *, save):
        require(self.refs == {s: reference(c) for s, c in stereo.cameras.items()},
                "Render advanced between stereo acquisitions")
        require(compute_counts(stereo.cameras) == self.counts_after, "Annotators changed during processing")
        require(abs(omni.timeline.get_timeline_interface().get_current_time() - time_s) < 1e-7,
                "Timeline moved while pair was captured")
        require(carb.settings.get_settings().get("/rtx/post/aa/op") == self.cfg["rtx"].get("antialiasing", 0), "AA did not persist")
        extrinsics = validate_geometry(self.stage, self.cfg["stereo"])
        require(all(np.allclose(extrinsics[s], self.extrinsics[s], atol=1e-6) for s in extrinsics),
                "Camera mount drift")
        products = {s: c.get_render_product_path() for s, c in stereo.cameras.items()}
        if self.products is None:
            self.products = products
        require(products == self.products, "Render products were recreated")
        checks, arrays = {}, {}
        for side, cam in stereo.cameras.items():
            rgba_gpu, depth_gpu, raw, depth = self.inputs[side]
            require(raw.shape == (480, 752, 4) and raw.dtype == np.uint8, "Invalid raw color")
            require(depth.shape == (480, 752) and depth.dtype == np.float32, "Invalid clean range")
            require(np.isfinite(depth).mean() > 0.9 and not np.isnan(depth).any(), "Missing tank geometry")
            require(np.array_equal(rgba_gpu.numpy(), raw), "Raw RGB changed during UW processing")
            require(np.array_equal(depth_gpu.numpy(), depth, equal_nan=True), "Clean depth changed")
            require(np.array_equal(pair[side], cam._uw_frame), "Recorder received different image")
            k = cam.get_intrinsics_matrix()
            try:
                geometry = check_geometry(self.stage, cam, raw, depth, k, side)
            except RuntimeError:
                write_png(self.directory / f"failed_{pass_name}_{index:06d}_{side}_raw.png", raw)
                raise
            checks[side] = {"geometry": geometry,
                            "underwater": check_underwater(cam, raw, depth),
                            "raw_rgb_mean": float(raw[..., :3].mean()),
                            "raw_rgb_std": float(raw[..., :3].std())}
            if save:
                label = f"{pass_name}_{index:06d}_{side}"
                write_png(self.directory / (label + "_raw.png"), raw)
                valid = np.isfinite(depth) & (depth > 0)
                visual = np.zeros(depth.shape + (3,), dtype=np.uint8)
                visual[valid] = (32 + 223 * np.clip(depth[valid, None] / 9, 0, 1)).astype(np.uint8)
                write_png(self.directory / (label + "_range.png"), visual)
                arrays.update({f"{side}_raw_rgba": raw, f"{side}_clean_range_m": depth,
                               f"{side}_underwater_rgba": pair[side],
                               f"{side}_degraded_range_m": cam._degraded_depth_frame})
        require(not np.shares_memory(pair["left"], pair["right"]), "Aliased stereo outputs")
        left, right = (checks[s]["geometry"] for s in ("left", "right"))
        expected = k[0, 0] * self.cfg["stereo"]["baseline_m"] / left["target_optical_xyz_m"][2]
        measured = left["measured_uv"][0] - right["measured_uv"][0]
        require(measured > 0 and abs(measured - expected) < CFG["pixel_tolerance"], "Disparity mismatch")
        require(abs(left["measured_uv"][1] - right["measured_uv"][1]) < 0.75, "Epipolar row mismatch")
        reconstructed = k[0, 0] * self.cfg["stereo"]["baseline_m"] / measured
        require(abs(reconstructed / left["target_optical_xyz_m"][2] - 1) < 0.03, "Stereo depth mismatch")
        checks["stereo"] = {"expected_disparity_px": float(expected), "measured_disparity_px": float(measured),
                            "known_optical_z_m": left["target_optical_xyz_m"][2],
                            "reconstructed_optical_z_m": float(reconstructed)}
        row = {"pass": pass_name, "frame": index, "simulation_time_s": time_s,
               "reference_time": self.refs, "compute_counts_before": self.counts_before,
               "compute_counts_after": self.counts_after, "checks": checks}
        self.rows.append(row)
        # Preserve partial evidence even if a later frame or shutdown fails.
        write_json(self.directory / "summary.json", {"status": "running", "target": CFG, "frames": self.rows})
        if save:
            np.savez_compressed(self.directory / f"{pass_name}_{index:06d}_frames.npz", **arrays)

    def finish(self):
        require(bool(self.rows), "No pairs validated")
        self.capture_overviews()
        write_json(self.directory / "summary.json", {"status": "PASS", "target": CFG,
                   "target_exposure_scale": self.target_exposure_scale,
                   "render_products": self.products, "T_body_optical": self.extrinsics, "frames": self.rows,
                   "scope": "Configured tank/inspection lighting plus one exposure-normalized emissive diagnostic target. Raw RGB and radial range readback only in this opt-in test. Freshness by per-annotator compute counts, matching ReferenceTime and pose reprojection."})

    def capture_overviews(self):
        """Inspection views after recording; no extra product during stereo capture."""
        import omni.replicator.core as rep
        from rov_sim.robots.bluerov import set_pose
        set_pose(self.stage, self.cfg["robot"]["position_m"], self.cfg["robot"]["rotation_xyz_deg"])
        camera = UsdGeom.Camera.Define(self.stage, "/World/DiagnosticOverview")
        transform = camera.AddTransformOp()
        camera.GetFocalLengthAttr().Set(24)
        camera.GetHorizontalApertureAttr().Set(36)
        camera.GetVerticalApertureAttr().Set(36 * 700 / 1000)
        camera.GetClippingRangeAttr().Set(Gf.Vec2f(0.1, 100))
        self.overview_product = rep.create.render_product(str(camera.GetPath()), (1000, 700))
        self.overview_annot = rep.AnnotatorRegistry.get_annotator("LdrColor", device="cpu")
        self.overview_annot.attach(self.overview_product)
        water = UsdGeom.Imageable(self.stage.GetPrimAtPath("/World/Water"))
        fill = None
        try:
            for label, eye, target, dry, focal in (
                ("tank_wet_overview", (-7, -8, 7), (0, 0, 1.2), False, 24),
                ("tank_dry_inspection", (-7, -8, 7), (0, 0, 1.2), True, 24),
                ("vehicle_dry_inspection", (-1.8, -1.3, 2.4), (-3.1, 0, 1.35), True, 50),
            ):
                if dry and fill is None:
                    water.MakeInvisible()
                    fill = UsdLux.DomeLight.Define(self.stage, "/World/DiagnosticInspectionFill")
                    fill.CreateIntensityAttr(1000)
                transform.Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target),
                                                    Gf.Vec3d(0, 0, 1)).GetInverse())
                camera.GetFocalLengthAttr().Set(focal)
                for _ in range(10):
                    rep.orchestrator.step(rt_subframes=1, delta_time=0.0, pause_timeline=True, wait_for_render=True)
                write_png(self.directory / (label + ".png"), self.overview_annot.get_data())
        finally:
            water.MakeVisible()
            if fill is not None:
                fill.GetIntensityAttr().Set(0)

    def close(self):
        # Called after STOP has been delivered, before renderer shutdown.
        if self.overview_annot is not None:
            self.overview_annot.detach(self.overview_product)
        if self.overview_product is not None:
            self.overview_product.destroy()


