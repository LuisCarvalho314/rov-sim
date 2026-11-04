"""OpenUSD helpers preserved from rov_tank_builder.py."""
from pxr import Gf, Usd, UsdGeom, UsdPhysics, Vt


def group(stage: Usd.Stage, path: str) -> UsdGeom.Xform:
    """Create a transform parent to keep the Stage tree organised."""
    return UsdGeom.Xform.Define(stage, path)


def rgb(geom, colour: tuple[float, float, float]) -> None:
    """Simple display colour. Replace with USD/MDL materials for realism."""
    geom.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*colour)]))


def box(stage, path, xyz, size_xyz, colour, *, collision=True):
    """Create an axis-aligned cube of a given centre and dimensions in metres.

    Because the USD cube has size 1, scaling each axis by size_xyz gives the
    actual dimensions. Child transforms are local to their parent Xform.
    """
    prim = UsdGeom.Cube.Define(stage, path)
    prim.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(prim.GetPrim())
    xf.AddTranslateOp().Set(Gf.Vec3d(*xyz))
    xf.AddScaleOp().Set(Gf.Vec3f(*size_xyz))
    rgb(prim, colour)
    if collision:
        UsdPhysics.CollisionAPI.Apply(prim.GetPrim())
    return prim


def pipe(stage, path, xyz, *, diameter, length, colour, axis="z"):
    """Create a solid cylinder as a stand-in for a pipe.

    It is NOT hollow: substitute your own mesh/asset for higher fidelity.
    """
    angles = {
        "x": (0.0, 90.0, 0.0),
        "y": (-90.0, 0.0, 0.0),
        "z": (0.0, 0.0, 0.0),
    }
    prim = UsdGeom.Cylinder.Define(stage, path)
    prim.CreateRadiusAttr(0.5)
    prim.CreateHeightAttr(1.0)
    xf = UsdGeom.Xformable(prim.GetPrim())
    xf.AddTranslateOp().Set(Gf.Vec3d(*xyz))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(*angles[axis]))
    xf.AddScaleOp().Set(Gf.Vec3f(diameter, diameter, length))
    rgb(prim, colour)
    UsdPhysics.CollisionAPI.Apply(prim.GetPrim())
    return prim
