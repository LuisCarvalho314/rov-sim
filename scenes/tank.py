"""Construct the original inspection tank once on the active Kit stage."""
from pxr import Gf, Sdf, UsdGeom, UsdLux

from .equipment import build_changed_object, build_fixed_equipment
from .primitives import box, group


def build_tank(stage, cfg):
    w, l, h = cfg["dimensions_m"]
    t, colour = cfg["wall_thickness_m"], cfg["colour"]
    box(stage, "/World/Tank/Floor", (0, 0, -t / 2), (w, l, t), colour)
    for name, xyz, size in (
        ("East", (w / 2, 0, h / 2), (t, l, h)),
        ("West", (-w / 2, 0, h / 2), (t, l, h)),
        ("North", (0, l / 2, h / 2), (w, t, h)),
        ("South", (0, -l / 2, h / 2), (w, t, h)),
    ):
        box(stage, f"/World/Tank/Wall{name}", xyz, size, colour)


def build_lighting(stage, cfg):
    lighting = cfg["lighting"]
    for i, (x, y) in enumerate(lighting["positions_xy_m"]):
        light = UsdLux.RectLight.Define(stage, f"/World/Lighting/RectLight_{i}")
        light.CreateWidthAttr(lighting["size_m"][0])
        light.CreateHeightAttr(lighting["size_m"][1])
        light.CreateIntensityAttr(lighting["intensity"])
        light.CreateColorAttr(Gf.Vec3f(*lighting["colour"]))
        UsdGeom.XformCommonAPI(light).SetTranslate(Gf.Vec3d(
            x, y, cfg["tank"]["dimensions_m"][2] + lighting["height_above_tank_m"]
        ))
        # Verified in installed omni.kit.property.light 1.0.12:
        # prim_light_widget.py adds exactly this custom property for RectLight.
        light.GetPrim().CreateAttribute("light:enableCaustics", Sdf.ValueTypeNames.Bool).Set(cfg["rtx"]["caustics"])


def build_scene(stage, cfg):
    if stage.GetPrimAtPath("/World/Tank"):
        raise RuntimeError("Tank already exists; build the stage only once")
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = group(stage, "/World")
    stage.SetDefaultPrim(root.GetPrim())
    for name in ("Tank", "FixedEquipment", "Changes", "Lighting"):
        group(stage, f"/World/{name}")
    build_tank(stage, cfg["tank"])
    build_fixed_equipment(stage)
    build_changed_object(stage, cfg["changes"]["before_position_m"])
    build_lighting(stage, cfg)
