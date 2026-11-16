"""OceanSim refractive surface and source-verified legacy RTX caustics controls."""
from __future__ import annotations

import warnings

import carb.settings
from pxr import UsdShade


def configure_rtx(cfg):
    settings = carb.settings.get_settings()
    renderer = cfg["runtime"]["renderer"]
    # Kit 110 can replace SimulationApp's AA=0 with its startup DLSS preset.
    # Allow AA-off and reapply the existing requested value after bootstrap.
    if settings.get("/rtx-transient/post/aa/limitedOps") is not None:
        settings.set("/rtx-transient/post/aa/limitedOps", False)
    antialiasing = cfg["rtx"].get("antialiasing", 0)
    settings.set("/rtx/post/aa/op", antialiasing)
    if renderer == "RaytracedLighting":
        settings.set("/rtx/caustics/enabled", cfg["rtx"]["caustics"])
    # Permit tuning only keys actually registered by the running Kit build.
    for key, value in cfg["rtx"]["settings"].items():
        if not key.startswith("/rtx/") or settings.get(key) is None:
            raise ValueError(f"RTX setting is not registered in this build: {key}")
        settings.set(key, value)
    report = {
        "backend_requested": cfg["runtime"]["backend"],
        "app_vulkan": settings.get("/app/vulkan"),
        "graphics_backend_setting_readback": "vulkan" if settings.get("/app/vulkan") else "d3d12",
        "graphics_backend_runtime_confirmed": False,
        "renderer_requested": renderer,
        "renderer_readback": settings.get("/rtx/rendermode"),
        "rt2_enabled_readback": settings.get("/persistent/rtx/modes/rt2/enabled"),
        "dlss_aa_readback": settings.get("/rtx/post/aa/op"),
        "rt_subframes": cfg["simulation"]["rt_subframes"],
        "processed_stereo_frame": False,
        "compatibility_warnings": ["Graphics API and water refraction require Kit log and image inspection."],
        "photon_caustics_requested": cfg["rtx"]["caustics"],
        "legacy_photon_caustics_config": {
            "enabled": cfg["rtx"]["caustics"] if renderer == "RaytracedLighting" else False,
            "photon_count_multiplier": cfg["rtx"]["photon_count_multiplier"],
            "photon_max_bounces": cfg["rtx"]["photon_max_bounces"],
            "filter_steps": cfg["rtx"]["filter_steps"],
        },
        "physical_caustics_validation": (
            "UNVERIFIED: inspect illuminated floor through the refractive surface"
            if cfg["rtx"]["caustics"] else "not requested"
        ),
    }
    expected_vulkan = cfg["runtime"]["backend"] == "vulkan"
    if report["app_vulkan"] != expected_vulkan:
        raise RuntimeError(f"Graphics backend setting does not match launch configuration: {report}")
    if report["renderer_readback"] != renderer:
        raise RuntimeError(f"RTX renderer setting did not persist: {report}")
    if renderer == "RealTimePathTracing" and report["rt2_enabled_readback"] is not True:
        raise RuntimeError(f"RTX Real-Time 2.0 was not enabled by Kit at startup: {report}")
    if renderer == "RealTimePathTracing":
        report["compatibility_warnings"].append("Legacy photon caustics are unavailable in RTX Real-Time 2.0; water appearance may differ.")
    if report["dlss_aa_readback"] != antialiasing:
        raise RuntimeError(f"Antialiasing setting did not persist: {report}")
    if cfg["rtx"]["caustics"]:
        warnings.warn("RTX photon caustics requested for legacy RaytracedLighting. Settings readback does not prove backend/GPU support; validate the visible caustics on Windows.")
    return report


class UnderwaterEnvironment:
    def __init__(self, stage, cfg):
        from isaacsim.oceansim.watersurface import WaterSurface

        if stage.GetPrimAtPath("/World/Water"):
            raise RuntimeError("Water already exists; keep the original WaterSurface instance for animation")
        self.cfg = cfg
        water = cfg["water"]
        # Avoid OceanSim's constructor default of 500x1024 photons per light;
        # set the requested budget once after mesh/material construction.
        self.surface = WaterSurface(
            prim_path="/World/Water", name="inspection_tank_water",
            position=[0, 0, water["height_m"]], size=water["size_m"],
            dim=water["grid_resolution"], enable_caustics=False,
            cast_shadows=water["cast_shadows"],
        )
        if cfg["rtx"]["caustics"]:
            self.surface.set_caustics(
                photonCountMultiplier=cfg["rtx"]["photon_count_multiplier"],
                photonMaxBounces=cfg["rtx"]["photon_max_bounces"],
                eawFilteringSteps=cfg["rtx"]["filter_steps"],
            )
        self.update(0, force=True)
        prim = stage.GetPrimAtPath("/World/Water")
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if not material:
            raise RuntimeError("OceanSim water did not receive its refractive material")
        self.material_path = str(material.GetPath())
        from pxr import Gf, Sdf
        # Override only exposed MDL inputs on this stage, never OceanSim files.
        shader = UsdShade.Shader(material.GetPrim().GetChild("Shader"))
        for name, value in water.get("material", {}).items():
            if name == "transmission_color":
                shader.CreateInput(name, Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*value))
            else:
                shader.CreateInput(name, Sdf.ValueTypeNames.Float).Set(float(value))

    def update(self, time_s, *, force=False):
        wave = self.cfg["water"]["wave"]
        if force or wave["animated"]:
            if wave["amplitude_m"] == 0:
                return  # Preserve flat grid; OceanSim deform clamps amplitude > 0.
            self.surface.deform(
                time=wave["initial_time_s"] + (time_s if wave["animated"] else 0),
                amplitude=wave["amplitude_m"], windSpeed=wave["wind_speed_m_s"],
                waterDepth=max(1.0, self.cfg["water"]["height_m"]), scale=wave["scale"],
            )

    def close(self):
        # WaterSurface has no close() or event subscription in this version.
        # Releasing its Warp arrays before SimulationApp.close is sufficient.
        self.surface = None
