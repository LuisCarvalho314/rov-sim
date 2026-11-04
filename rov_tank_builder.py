"""Reusable underwater inspection tank template for Isaac Sim + OceanSim.

RUN IN ISAAC SIM'S *SCRIPT EDITOR* (NOT POWERSHELL):

    exec(open(r"C:\\issacsim-environments\\rov_tank_builder.py", encoding="utf-8").read(), globals())

Creates in OUTPUT_DIR:
    tank_before_rtx.usda       original scene with OceanSim water
    tank_after_rtx.usda        identical scene, movable crate shifted 0.5 m
    scene_manifest.json       experiment metadata and approximate calibration

The script has TWO PHASES:
    1) Standard OpenUSD APIs create both stages, geometry, lights and cameras.
    2) The stages are opened in Isaac Sim; OceanSim's WaterSurface attaches its
       actual MDL water material to the *active stage*, and we save each stage.

IMPORTANT LIMITATIONS:
    - 'Water' is a visual surface, not a fluid volume or buoyancy simulation.
    - Underwater colour attenuation/backscatter still requires OceanSim UW_Camera.
    - RTX photon caustics depend on the active RTX renderer mode and light
      settings. The per-light property should be checked in the Isaac Sim GUI.
    - This template has not been executed against your local Isaac Sim build.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path

import carb.settings
import omni.kit.app
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, Vt


# =============================================================================
# 1. CONFIGURATION -- EDIT THESE FIRST
# =============================================================================
@dataclass(frozen=True)
class Config:
    # Intentionally separate from the old C:\rov_sim\scenes output: this script
    # never modifies the two dry tank scenes you built previously.
    output_dir: Path = Path(r"C:\issacsim-environments\generated_tank")

    # Existing generated files are preserved unless you deliberately opt in.
    overwrite_generated_files: bool = False

    # Z is up; the floor surface is z=0. Water fills the visual tank to z=2.85.
    tank_width_m: float = 8.0       # x
    tank_length_m: float = 5.0      # y
    tank_height_m: float = 3.0      # z
    wall_thickness_m: float = 0.20
    water_height_m: float = 2.85

    # Stereo calibration. Poses are identical between inspection sessions.
    image_width_px: int = 752
    image_height_px: int = 480
    stereo_baseline_m: float = 0.38
    focal_length_mm: float = 15.0
    horizontal_aperture_mm: float = 21.0

    # BEFORE and AFTER describe a pure translation of ONE logical object.
    crate_before_xyz: tuple[float, float, float] = (1.15, -0.65, 0.30)
    crate_after_xyz: tuple[float, float, float] = (1.65, -0.65, 0.30)

    # Small water waves make caustics visible but don't obscure the tank.
    water_grid_resolution: tuple[int, int] = (80, 50)
    initial_wave_amplitude_m: float = 0.06
    initial_wave_time_s: float = 0.0

    # RTX *LEGACY real-time* photon caustics. These controls are specifically
    # documented for the legacy renderer, not a promise for Real-Time 2.0.
    # 40 ~= 40 x 1024 photons PER LIGHT, not 40 photons in total.
    photon_count_multiplier: int = 40
    photon_max_bounces: int = 4
    caustics_filter_steps: int = 5

    # True: request the documented legacy RTX real-time photon-caustics mode.
    # If that mode is unavailable, set False and select a working RTX renderer
    # manually; the legacy photon-caustics settings may not apply to RT 2.0.
    request_legacy_renderer: bool = True

    # Area lights sit ABOVE the water surface, facing down by default.
    area_light_intensity: float = 950.0


CFG = Config()
BEFORE_FILE = "tank_before_rtx.usda"
AFTER_FILE = "tank_after_rtx.usda"
MANIFEST_FILE = "scene_manifest.json"


# =============================================================================
# 2. REUSABLE OPENUSD HELPERS -- NO OCEANSIM DEPENDENCY IN THIS SECTION
# =============================================================================
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


def add_camera(stage, path, lateral_offset):
    """Add USD stereo camera prim, facing local -Z, with +Y as image up."""
    cam = UsdGeom.Camera.Define(stage, path)
    cam.CreateFocalLengthAttr(CFG.focal_length_mm)
    cam.CreateHorizontalApertureAttr(CFG.horizontal_aperture_mm)
    cam.CreateVerticalApertureAttr(
        CFG.horizontal_aperture_mm * CFG.image_height_px / CFG.image_width_px
    )
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 25.0))
    UsdGeom.Xformable(cam.GetPrim()).AddTranslateOp().Set(
        Gf.Vec3d(lateral_offset, 0, 0)
    )
    return cam


# =============================================================================
# 3. SCENE COMPONENTS -- EDIT/EXTEND THESE TO DESIGN YOUR OWN ENVIRONMENT
# =============================================================================
def build_tank(stage):
    """Concrete floor + open-topped walls; ALL measurements are metres."""
    w, l, h, t = (CFG.tank_width_m, CFG.tank_length_m,
                  CFG.tank_height_m, CFG.wall_thickness_m)
    c = (0.38, 0.42, 0.43)
    box(stage, "/World/Tank/Floor", (0, 0, -t / 2), (w, l, t), c)
    box(stage, "/World/Tank/WallEast", (w / 2, 0, h / 2), (t, l, h), c)
    box(stage, "/World/Tank/WallWest", (-w / 2, 0, h / 2), (t, l, h), c)
    box(stage, "/World/Tank/WallNorth", (0, l / 2, h / 2), (w, t, h), c)
    box(stage, "/World/Tank/WallSouth", (0, -l / 2, h / 2), (w, t, h), c)


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


def build_stereo_rig(stage):
    """Create the paired camera prims under one transform for trajectory replay.

    A shared rig transform preserves relative camera calibration. Later, your
    inspection trajectory should modify /World/CameraRig, not each camera.
    """
    rig_prim = stage.GetPrimAtPath("/World/CameraRig")
    eye, look_at = Gf.Vec3d(-3.10, 0.0, 1.35), Gf.Vec3d(0.9, 0.0, 1.25)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(eye, look_at, Gf.Vec3d(0.0, 0.0, 1.0))
    UsdGeom.Xformable(rig_prim).AddTransformOp().Set(view.GetInverse())
    add_camera(stage, "/World/CameraRig/Left", -CFG.stereo_baseline_m / 2)
    add_camera(stage, "/World/CameraRig/Right", CFG.stereo_baseline_m / 2)


def build_lighting(stage):
    """Over-water illumination for RTX caustics.

    RTX caustics require suitable refractive water, appropriate renderer and
    source-light caustics settings; creating two RectLights is not sufficient.
    """
    for i, (x, y) in enumerate(((-1.25, -0.80), (1.80, 1.00))):
        light = UsdLux.RectLight.Define(
            stage, f"/World/Lighting/RectLight_{i}"
        )
        light.CreateWidthAttr(2.20)
        light.CreateHeightAttr(1.50)
        light.CreateIntensityAttr(CFG.area_light_intensity)
        light.CreateColorAttr(Gf.Vec3f(0.83, 0.92, 1.00))
        # The default normal points along -Z, from light toward water.
        UsdGeom.Xformable(light.GetPrim()).AddTranslateOp().Set(
            Gf.Vec3d(x, y, CFG.tank_height_m + 0.35)
        )

        # In many Omniverse releases RTX exposes an 'Enable Caustics' property
        # on the light itself. Author the commonly used USD input explicitly;
        # verify in the light's Property panel that the renderer recognises it.
        # This is a best-effort property, NOT a guarantee of renderer support.
        light.GetPrim().CreateAttribute(
            "inputs:enableCaustics", Sdf.ValueTypeNames.Bool
        ).Set(True)


def write_base_stage(path, moved_object_xyz):
    """Make a completely separate, deterministic USD stage (no live Kit state)."""
    stage = Usd.Stage.CreateNew(path.as_posix())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = group(stage, "/World")
    stage.SetDefaultPrim(root.GetPrim())
    for name in ("Tank", "FixedEquipment", "Changes", "CameraRig", "Lighting"):
        group(stage, f"/World/{name}")

    physics = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
    physics.CreateGravityMagnitudeAttr(9.81)
    build_tank(stage)
    build_fixed_equipment(stage)
    build_changed_object(stage, moved_object_xyz)
    build_stereo_rig(stage)
    build_lighting(stage)
    stage.GetRootLayer().Save()


# =============================================================================
# 4. OCEANSIM FINISHING PASS -- REQUIRES AN ACTIVE ISAAC SIM STAGE
# =============================================================================
def set_rtx_renderer_settings():
    """Configure RTX *Legacy* photon caustics for the current Isaac Sim app.

    RTX settings are APPLICATION state, not geometry stored in a USD file.
    Reapply these settings when you launch a new Isaac Sim session.
    """
    settings = carb.settings.get_settings()
    if CFG.request_legacy_renderer:
        settings.set("/rtx/rendermode", "RaytracedLighting")
    settings.set("/rtx/caustics/enabled", True)
    settings.set("/rtx/raytracing/caustics/photonCountMultiplier",
                 CFG.photon_count_multiplier)
    settings.set("/rtx/raytracing/caustics/photonMaxBounces",
                 CFG.photon_max_bounces)
    settings.set("/rtx/raytracing/caustics/eawFilteringSteps",
                 CFG.caustics_filter_steps)
    print("[RTX] Requested caustics; active renderer:",
          settings.get("/rtx/rendermode"))


def attach_oceansim_water():
    """Create OceanSim's *actual MDL water surface*, not a coloured plane.

    OceanSim WaterSurface currently relies on get_current_stage(),
    an MDL material provided by the extension and GPU Warp kernels.
    It cannot correctly be constructed on an inactive Usd.Stage.CreateNew().
    """
    from isaacsim.oceansim.watersurface import WaterSurface

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("There is no active USD stage in Isaac Sim.")
    if stage.GetPrimAtPath("/World/Water").IsValid():
        raise RuntimeError("/World/Water already exists. Not adding duplicate water.")

    # Keep surface slightly INSIDE tank boundaries, away from wall meshes.
    surface_size = (
        CFG.tank_width_m - CFG.wall_thickness_m * 2,
        CFG.tank_length_m - CFG.wall_thickness_m * 2,
    )
    water = WaterSurface(
        prim_path="/World/Water",
        name="inspection_tank_water",
        position=[0.0, 0.0, CFG.water_height_m],
        size=list(surface_size),
        dim=list(CFG.water_grid_resolution),
        enable_caustics=True,
        cast_shadows=True,
    )
    # Small, deterministic initial surface deformation. The mesh is saved
    # into the USD; a *moving* surface needs the optional runtime helper below.
    water.deform(
        time=CFG.initial_wave_time_s,
        amplitude=CFG.initial_wave_amplitude_m,
        windSpeed=2.0,
        waterDepth=max(1.0, CFG.water_height_m),
        scale=1.0,
    )
    water.set_caustics(
        photonCountMultiplier=CFG.photon_count_multiplier,
        photonMaxBounces=CFG.photon_max_bounces,
        eawFilteringSteps=CFG.caustics_filter_steps,
    )
    return water


def make_manifest():
    """Calibration metadata; verify real sensor intrinsics before SLAM."""
    fx = CFG.focal_length_mm / CFG.horizontal_aperture_mm * CFG.image_width_px
    fy = fx  # proportional aperture choice gives square pixel approximation
    payload = {
        "unit": "metre",
        "up_axis": "Z",
        "tank_dimensions_m": [CFG.tank_width_m, CFG.tank_length_m,
                              CFG.tank_height_m],
        "waterline_z_m": CFG.water_height_m,
        "before_usd": BEFORE_FILE,
        "after_usd": AFTER_FILE,
        "changed_prim": "/World/Changes/MovableCrate",
        "before_position_m": list(CFG.crate_before_xyz),
        "after_position_m": list(CFG.crate_after_xyz),
        "displacement_m": math.dist(CFG.crate_before_xyz,
                                     CFG.crate_after_xyz),
        "camera_rig_prim": "/World/CameraRig",
        "left_camera_prim": "/World/CameraRig/Left",
        "right_camera_prim": "/World/CameraRig/Right",
        "image_wh": [CFG.image_width_px, CFG.image_height_px],
        "baseline_m": CFG.stereo_baseline_m,
        "K_approx": [
            [fx, 0.0, CFG.image_width_px / 2],
            [0.0, fy, CFG.image_height_px / 2],
            [0.0, 0.0, 1.0],
        ],
        "caveats": [
            "K is estimated from USD camera attributes; verify against camera_info.",
            "RTX caustics settings are app state, not guaranteed by the saved USD.",
            "OceanSim UW_Camera is required for underwater attenuation/backscatter.",
            "The two USD stages contain identical background, lights and water geometry.",
        ],
    }
    (CFG.output_dir / MANIFEST_FILE).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# =============================================================================
# 5. MAIN BUILDER -- AN ASYNC TASK BECAUSE KIT MUST OPEN EACH STAGE
# =============================================================================
async def build_tank_scenes():
    """Generate both before/after USD files and attach real OceanSim water."""
    paths = [CFG.output_dir / BEFORE_FILE, CFG.output_dir / AFTER_FILE]
    CFG.output_dir.mkdir(parents=True, exist_ok=True)
    if not CFG.overwrite_generated_files:
        existing = [str(p) for p in paths if p.exists()]
        if existing:
            raise FileExistsError(
                "Generated files already exist; edit Config.output_dir or set "
                "overwrite_generated_files=True if you intend to replace them: "
                + ", ".join(existing)
            )
    else:
        for p in paths:
            if p.exists():
                p.unlink()

    print("[1/3] Generating base OpenUSD tank scenes...")
    write_base_stage(paths[0], CFG.crate_before_xyz)
    write_base_stage(paths[1], CFG.crate_after_xyz)

    print("[2/3] Opening each stage and applying OceanSim water...")
    ctx = omni.usd.get_context()
    set_rtx_renderer_settings()
    for path in paths:
        success, error = await ctx.open_stage_async(path.as_posix())
        if not success:
            raise RuntimeError(f"Could not open {path}: {error}")
        await omni.kit.app.get_app().next_update_async()
        water = attach_oceansim_water()
        ctx.get_stage().GetRootLayer().Save()
        print("[OceanSim] Saved:", path)
        # Let Kit render one frame before changing scenes, and release the
        # object; its authored geometry+MDL binding are already in the USD.
        await omni.kit.app.get_app().next_update_async()
        del water

    make_manifest()
    print("[3/3] Opening BEFORE stage for inspection...")
    success, error = await ctx.open_stage_async(paths[0].as_posix())
    if not success:
        raise RuntimeError(f"Could not reopen {paths[0]}: {error}")
    set_rtx_renderer_settings()
    print("[DONE] Both scenes contain OceanSim water and RTX-ready lights.")
    print("[DONE] Output directory:", CFG.output_dir)
    print("[NEXT] Inspect the surface material and each light's Enable Caustics "
          "toggle in the Property panel. Use RTX Real-Time (Legacy) for the "
          "documented photon-caustics controls.")
    print("[NEXT] UW_Camera is still needed for underwater stereo degradation.")


# =============================================================================
# 6. EXECUTION -- FROM ISAAC SIM SCRIPT EDITOR
# =============================================================================
# Keep the coroutine Task alive. The Script Editor returns immediately, then
# Isaac Sim processes the two stages in its existing application event loop.
# Watch the Script Editor/Console for [1/3], [2/3], [3/3], [DONE] messages.
#
# For live surface deformation, use OceanSim's Color Picker (which owns an
# appropriate WaterSurface instance and update callback), or add a separate
# runtime animation module. Do not repeatedly construct WaterSurface on an
# already existing prim merely to animate it: that may recreate its geometry.
ROV_TANK_TASK = asyncio.ensure_future(build_tank_scenes())
