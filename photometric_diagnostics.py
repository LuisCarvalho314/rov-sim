"""Target-free evidence capture around the existing simulator and OceanSim path."""
from pathlib import Path

import carb.settings
import numpy as np
from pxr import Usd, UsdGeom, UsdShade

from recording import write_json, write_png


class PhotometricCapture:
    def __init__(self, stage, cfg, directory):
        self.directory = Path(directory) / "photometry"
        self.directory.mkdir()
        settings = carb.settings.get_settings()
        keys = ("/rtx/post/aa/op", "/rtx/post/tonemap/op", "/rtx/post/tonemap/filmIso",
                "/rtx/post/tonemap/cameraShutter", "/rtx/post/tonemap/fNumber",
                "/rtx/post/tonemap/exposureTime", "/rtx/post/tonemap/cm2Factor",
                "/rtx/post/histogram/enabled", "/rtx/post/dlss/execMode",
                "/rtx/raytracing/cached/enabled", "/rtx/rtpt/gi/enabled")
        geometry = []
        for prim in stage.Traverse():
            if prim.IsA(UsdGeom.Mesh):
                mesh = UsdGeom.Mesh(prim)
                normals = mesh.GetNormalsAttr().Get()
                geometry.append({"path": str(prim.GetPath()),
                                 "points": len(mesh.GetPointsAttr().Get() or []),
                                 "normals": len(normals or []),
                                 "normal_interpolation": mesh.GetNormalsInterpolation()})
        water = stage.GetPrimAtPath("/World/Water")
        material, _ = UsdShade.MaterialBindingAPI(water).ComputeBoundMaterial()
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
        bounds = {}
        for prim in stage.Traverse():
            if str(prim.GetPath()).startswith("/World/FixedEquipment/") and prim.IsA(UsdGeom.Gprim):
                box = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                bounds[str(prim.GetPath())] = [list(box.GetMin()), list(box.GetMax())]
        write_json(self.directory / "scene_evidence.json", {
            "settings": {k: settings.get(k) for k in keys}, "meshes": geometry, "equipment_bounds": bounds,
            "water_material": str(material.GetPath()),
            "target_present": bool(stage.GetPrimAtPath("/World/DiagnosticTarget")),
            "scope": "Original scene; no added geometry or emissive targets. Raw is RTX LDR before OceanSim."})

    def capture(self, stereo, pair, pass_name, index):
        from stereo_diagnostics import reference
        refs = {side: reference(camera) for side, camera in stereo.cameras.items()}
        if refs["left"] != refs["right"]:
            raise RuntimeError("Unsynchronized photometric capture")
        arrays = {}
        for side, camera in stereo.cameras.items():
            raw = camera._rgba_annot.get_data().numpy().copy()
            depth = camera._depth_annot.get_data().numpy().copy()
            arrays[f"{side}_raw_rgba"] = raw
            arrays[f"{side}_clean_range_m"] = depth
            arrays[f"{side}_underwater_rgba"] = pair[side]
            write_png(self.directory / f"{pass_name}_{index:06d}_{side}_raw.png", raw)
        np.savez_compressed(self.directory / f"{pass_name}_{index:06d}.npz", **arrays)
        write_json(self.directory / f"{pass_name}_{index:06d}_metadata.json", {
            "reference_time": refs, "aa_readback": carb.settings.get_settings().get("/rtx/post/aa/op"),
            "equivalent_input_processing": (stereo.validate_equivalent_processing()
                                             if hasattr(stereo, "validate_equivalent_processing") else None)})
