"""Kinematic vehicle carrier with independent asset alignment and sensor mount."""
from pathlib import Path

from pxr import Gf, Usd, UsdGeom, UsdPhysics

VEHICLE_PATH = "/World/BlueROV"


def set_pose(stage, position_m, rotation_xyz_deg):
    api = UsdGeom.XformCommonAPI(stage.GetPrimAtPath(VEHICLE_PATH))
    api.SetTranslate(Gf.Vec3d(*position_m))
    api.SetRotate(Gf.Vec3f(*rotation_xyz_deg))


def build_bluerov(stage, cfg):
    from isaacsim.oceansim.utils.assets_utils import get_oceansim_assets_path

    if stage.GetPrimAtPath(VEHICLE_PATH):
        raise RuntimeError("BlueROV already exists")
    asset = Path(get_oceansim_assets_path()) / cfg["asset"]
    if not asset.is_file():
        raise FileNotFoundError(f"Registered OceanSim asset is missing: {asset}")
    asset_stage = Usd.Stage.Open(str(asset))
    if asset_stage is None or not asset_stage.GetDefaultPrim():
        raise RuntimeError(f"BlueROV asset has no usable default prim: {asset}")
    units = UsdGeom.GetStageMetersPerUnit(asset_stage)
    up_axis = str(UsdGeom.GetStageUpAxis(asset_stage))

    carrier = UsdGeom.Xform.Define(stage, VEHICLE_PATH)
    set_pose(stage, cfg["position_m"], cfg["rotation_xyz_deg"])
    alignment = UsdGeom.Xform.Define(stage, VEHICLE_PATH + "/ModelAlignment")
    model = cfg["model"]
    api = UsdGeom.XformCommonAPI(alignment)
    api.SetTranslate(Gf.Vec3d(*model["position_m"]))
    api.SetRotate(Gf.Vec3f(*model["rotation_xyz_deg"]))
    api.SetScale(Gf.Vec3f(*(s * units for s in model["scale"])))
    # USD references do not convert a referenced layer's units or up axis.
    conversion = UsdGeom.Xform.Define(stage, str(alignment.GetPath()) + "/UpAxis")
    if up_axis == "Y":
        UsdGeom.XformCommonAPI(conversion).SetRotate(Gf.Vec3f(90, 0, 0))
    elif up_axis != "Z":
        raise RuntimeError(f"Unsupported asset up axis: {up_axis}")
    referenced = stage.DefinePrim(str(conversion.GetPath()) + "/Asset", "Xform")
    if not referenced.GetReferences().AddReference(asset.as_posix()):
        raise RuntimeError(f"Could not reference {asset}")
    if not any(p.IsA(UsdGeom.Mesh) for p in Usd.PrimRange(referenced)):
        raise RuntimeError("BlueROV reference contains no meshes")
    # Drive one USD parent. Disable any referenced body physics so authored
    # asset bodies cannot fall, move independently or overwrite these poses.
    for prim in Usd.PrimRange(referenced):
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            raise RuntimeError("Unexpected articulated BlueROV asset; inspect its physics before using it")
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            UsdPhysics.RigidBodyAPI(prim).CreateRigidBodyEnabledAttr(False)
    body = UsdPhysics.RigidBodyAPI.Apply(carrier.GetPrim())
    body.CreateRigidBodyEnabledAttr(True)
    body.CreateKinematicEnabledAttr(True)
    bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    bounds = bbox.ComputeUntransformedBound(alignment.GetPrim()).ComputeAlignedRange()
    # ComputeUntransformedBound excludes alignment's scale; include it via the
    # world bound and report the initial world AABB used for visual inspection.
    world_bounds = bbox.ComputeWorldBound(alignment.GetPrim()).ComputeAlignedRange()
    size = list(world_bounds.GetSize())
    if not all(0.1 < s < 3.0 for s in size):
        raise RuntimeError(f"Implausible BlueROV size in metres: {size}. Check asset units and robot.model.scale.")
    print(f"[BlueROV] asset units={units} m, up={up_axis}, world AABB size={size}")
    return {
        "prim_path": VEHICLE_PATH, "asset": asset.as_posix(),
        "asset_meters_per_unit": units, "asset_up_axis": up_axis,
        "initial_world_aabb_size_m": size,
        "body_frame": "+X forward, +Y left, +Z up; model heading requires visual confirmation",
        "model_local_bounds": [list(bounds.GetMin()), list(bounds.GetMax())],
    }
