"""Kit launch and OceanSim registration; Kit imports stay inside functions."""
from __future__ import annotations

import os


def launch_options(cfg, headless, kit_args=()):
    backend = cfg["runtime"]["backend"]
    if backend == "d3d12" and os.name != "nt":
        raise RuntimeError("DirectX 12 requires Windows. Launch through PowerShell and Isaac Sim's python.bat.")
    extra = list(cfg["runtime"]["extra_args"]) + list(kit_args)
    # These must reach Kit before its graphics device is created. Isaac Sim's
    # Python experience otherwise explicitly enables Vulkan on Windows.
    extra.append(f"--/app/vulkan={'false' if backend == 'd3d12' else 'true'}")
    extra.append("--/app/player/useFixedTimeStepping=true")
    return {
        "headless": headless,
        "renderer": cfg["runtime"]["renderer"],
        "width": cfg["stereo"]["resolution"][0],
        "height": cfg["stereo"]["resolution"][1],
        "multi_gpu": False,
        "sync_loads": True,
        "fast_shutdown": False,
        "extra_args": extra,
    }


def enable_oceansim(app, directory):
    import omni.kit.app

    manager = omni.kit.app.get_app().get_extension_manager()
    manager.add_path(str(directory.parent))
    app.update()
    matches = [item for item in manager.get_extensions() if item["name"].lower() == directory.name.lower()]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one registered {directory.name} extension, found {matches}. Remove duplicate extension search paths.")
    extension_id = matches[0]["id"]
    from pathlib import Path
    registered = Path(manager.get_extension_path(extension_id)).resolve()
    if registered != directory.resolve():
        raise RuntimeError(f"OceanSim resolved to {registered}, requested {directory}. Remove duplicate registrations.")
    manager.set_extension_enabled_immediate(extension_id, True)
    app.update()
    if not manager.is_extension_enabled(extension_id):
        raise RuntimeError(f"Kit could not enable {extension_id}. Check the extension dependency errors in the Kit log.")
    from isaacsim.oceansim.sensors.UW_Camera import UW_Camera
    from isaacsim.oceansim.watersurface import WaterSurface
    from isaacsim.oceansim.utils.assets_utils import get_oceansim_assets_path

    import inspect
    for method, names in (
        (UW_Camera.initialize, ["UW_yaml_path", "viewport", "max_range", "depth_noise_sigma"]),
        (WaterSurface.__init__, ["size", "dim", "enable_caustics"]),
        (WaterSurface.deform, ["time", "amplitude", "windSpeed", "waterDepth"]),
        (WaterSurface.set_caustics, ["photonCountMultiplier", "photonMaxBounces", "eawFilteringSteps"]),
    ):
        if not set(names) <= set(inspect.signature(method).parameters):
            raise RuntimeError(f"Unsupported OceanSim API: {method.__qualname__}{inspect.signature(method)}")
    for name in ("render", "close", "destroy"):
        if not callable(getattr(UW_Camera, name, None)):
            raise RuntimeError(f"OceanSim camera lacks required {name}()")
    root = get_oceansim_assets_path()
    print(f"[OceanSim] {extension_id} at {registered}; assets: {root}")
    return {"extension_id": extension_id, "extension_directory": str(registered), "asset_root": root}
