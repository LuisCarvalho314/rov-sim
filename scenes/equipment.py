"""Original pipes, inspection panel, fixtures, markers and crates."""
from pxr import Gf, UsdGeom
from .primitives import box, group, pipe


def build_fixed_equipment(stage):
    """All geometry that must remain IDENTICAL between the two inspections."""
    metal, rust, blue = (0.33, 0.39, 0.43), (0.47, 0.27, 0.15), (0.15, 0.31, 0.45)

    # Repeated pipes are deliberate: they create visually aliased regions.
    for i, y in enumerate((-1.65, -0.75, 0.45, 1.40)):
        pipe(stage, f"/World/FixedEquipment/VerticalPipe_{i}",
             (3.62, y, 1.35), diameter=0.13, length=2.30, colour=metal)
        box(stage, f"/World/FixedEquipment/Bracket_{i}",
            (3.52, y, 0.60), (0.20, 0.25, 0.11), rust)

    pipe(stage, "/World/FixedEquipment/OverheadPipe", (1.25, 1.9, 2.45),
         diameter=0.18, length=4.30, colour=metal, axis="x")
    pipe(stage, "/World/FixedEquipment/FloorPipe", (1.05, -1.9, 0.18),
         diameter=0.22, length=4.70, colour=rust, axis="x")

    # Inspection panel: strips and bolts provide recoverable image features.
    box(stage, "/World/FixedEquipment/Panel", (3.77, -0.15, 1.65),
        (0.07, 0.95, 0.80), blue)
    for i, yy in enumerate((-0.44, -0.15, 0.14)):
        box(stage, f"/World/FixedEquipment/PanelStripe_{i}",
            (3.726, yy, 1.67), (0.025, 0.055, 0.53),
            (0.78, 0.77, 0.60), collision=False)
    for i, (yy, zz) in enumerate(((-0.53, 1.34), (0.23, 1.34),
                                 (-0.53, 1.96), (0.23, 1.96))):
        pipe(stage, f"/World/FixedEquipment/PanelBolt_{i}",
             (3.714, yy, zz), diameter=0.055, length=0.05,
             colour=metal, axis="x")

    box(stage, "/World/FixedEquipment/Platform", (0.75, 1.05, 0.14),
        (1.35, 0.95, 0.28), metal)
    box(stage, "/World/FixedEquipment/ReferenceCrate", (0.55, 1.00, 0.56),
        (0.65, 0.62, 0.55), rust)
    box(stage, "/World/FixedEquipment/ReferenceCrateRim", (0.55, 1.00, 0.85),
        (0.67, 0.64, 0.04), (0.16, 0.20, 0.21))

    for i, yy in enumerate((-1.5, -0.65, 0.2, 1.05)):
        box(stage, f"/World/FixedEquipment/RepeatedMarker_{i}",
            (3.745, yy, 2.65), (0.035, 0.25, 0.14),
            (0.80, 0.71, 0.38), collision=False)


def build_changed_object(stage, position):
    """A single movable parent Xform with multiple child meshes.

    For other change-detection experiments, move this parent, swap its asset,
    or add/remove subtrees under /World/Changes.
    """
    obj = group(stage, "/World/Changes/MovableCrate")
    UsdGeom.Xformable(obj.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*position))
    box(stage, "/World/Changes/MovableCrate/Body", (0, 0, 0),
        (0.62, 0.46, 0.60), (0.67, 0.36, 0.17))
    box(stage, "/World/Changes/MovableCrate/Lid", (0, 0, 0.31),
        (0.64, 0.48, 0.035), (0.34, 0.23, 0.18), collision=False)


def move_changed_object(stage, position):
    UsdGeom.XformCommonAPI(stage.GetPrimAtPath("/World/Changes/MovableCrate")).SetTranslate(Gf.Vec3d(*position))
