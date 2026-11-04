"""OceanSim refractive surface and source-verified legacy RTX caustics controls."""
from __future__ import annotations

import warnings

import carb.settings
from pxr import UsdShade


def configure_rtx(cfg):
    settings = carb.settings.get_settings()
    renderer = cfg["runtime"]["renderer"]
    settings.set("/rtx/rendermode", renderer)
    settings.set("/rtx/caustics/enabled", cfg["rtx"]["caustics"])
    # Permit tuning only keys actually registered by the running Kit build.
    for key, value in cfg["rtx"]["settings"].items():
        if not key.startswith("/rtx/") or settings.get(key) is None:
            raise ValueError(f"RTX setting is not registered in this build: {key}")
        settings.set(key, value)
    report = {
        "backend_requested": cfg["runtime"]["backend"],
        "app_vulkan": settings.get("/app/vulkan"),
        "renderer_requested": renderer,
        "renderer_readback": settings.get("/rtx/rendermode"),
        "photon_caustics_requested": cfg["rtx"]["caustics"],
        "physical_caustics_validation": "UNVERIFIED: check Kit graphics API log and inspect illuminated floor through the refractive surface",
    }
    expected_vulkan = cfg["runtime"]["backend"] == "vulkan"
    if report["app_vulkan"] != expected_vulkan:
        raise RuntimeError(f"Graphics backend setting does not match launch configuration: {report}")
    if report["renderer_readback"] != renderer:
        raise RuntimeError(f"RTX renderer setting did not persist: {report}")
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
