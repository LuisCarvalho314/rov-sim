"""Configuration and paths. Safe to import before SimulationApp starts."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def resolve_path(value, *, root=ROOT):
    expanded = os.path.expandvars(str(value))
    if "$" in expanded or ("%" in expanded and os.name == "nt"):
        raise ValueError(f"Unresolved environment variable in path: {value}")
    path = Path(expanded).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def load_config(path="configs/tank.yaml"):
    source = resolve_path(path)
    content = source.read_text(encoding="utf-8")
    try:
        # The shipped YAML uses JSON syntax (a YAML subset), so startup does
        # not depend on Kit having loaded OceanSim's PyYAML package yet.
        cfg = json.loads(content)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as error:
            raise ValueError("Use JSON-style YAML before Kit startup, or make PyYAML available to bundled Python.") from error
        cfg = yaml.safe_load(content)
    validate_config(cfg)
    return cfg


def validate_config(c):
    """Reject invalid geometry/calibration before allocating GPU resources."""
    def number(value, name, minimum=0, strict=True):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if value < minimum or (strict and value == minimum):
            raise ValueError(f"{name} must be {'greater than' if strict else 'at least'} {minimum}")

    def vector(value, name, length=3, positive=False):
        if not isinstance(value, list) or len(value) != length:
            raise ValueError(f"{name} must contain {length} numbers")
        for item in value:
            number(item, name, minimum=0 if positive else -math.inf)

    def integer(value, name, minimum=1):
        number(value, name, minimum, strict=False)
        if not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")

    try:
        tank, water, robot, stereo = (c[k] for k in ("tank", "water", "robot", "stereo"))
        for section, key in ((c["rtx"], "caustics"), (stereo, "preview"),
                             (water, "cast_shadows"), (water["wave"], "animated"),
                             (c["output"], "record_images")):
            if not isinstance(section[key], bool):
                raise ValueError(f"{key} must be true or false")
        if not isinstance(c["runtime"]["extra_args"], list) or not all(isinstance(v, str) for v in c["runtime"]["extra_args"]):
            raise ValueError("runtime.extra_args must be a list of strings")
        if not isinstance(c["rtx"]["settings"], dict):
            raise ValueError("rtx.settings must map registered RTX paths to values")
        vector(tank["dimensions_m"], "tank.dimensions_m", positive=True)
        vector(tank["colour"], "tank.colour")
        number(tank["wall_thickness_m"], "tank.wall_thickness_m")
        w, l, h = tank["dimensions_m"]
        if min(w, l) <= 2 * tank["wall_thickness_m"]:
            raise ValueError("Tank walls leave no interior space")
        number(water["height_m"], "water.height_m")
        if water["height_m"] >= h:
            raise ValueError("water.height_m must be below tank height")
        vector(water["size_m"], "water.size_m", 2, True)
        if any(a > b - tank["wall_thickness_m"] for a, b in zip(water["size_m"], (w, l))):
            raise ValueError("Water surface must fit inside the tank walls")
        vector(water["grid_resolution"], "water.grid_resolution", 2, True)
        for n in water["grid_resolution"]:
            integer(n, "water.grid_resolution")
        for pose in (robot, stereo["mount"], robot["model"]):
            vector(pose["position_m"], "pose.position_m")
            vector(pose["rotation_xyz_deg"], "pose.rotation_xyz_deg")
        vector(robot["model"]["scale"], "robot.model.scale", positive=True)
        x, y, z = robot["position_m"]
        if abs(x) >= w / 2 or abs(y) >= l / 2 or not 0 < z < water["height_m"]:
            raise ValueError("BlueROV origin must be inside the submerged tank")
        vector(stereo["resolution"], "stereo.resolution", 2, True)
        for n in stereo["resolution"]:
            integer(n, "stereo.resolution")
        for key in ("baseline_m", "focal_length_mm", "horizontal_aperture_mm"):
            number(stereo[key], f"stereo.{key}")
        vector(stereo["clipping_range_m"], "stereo.clipping_range_m", 2, True)
        if stereo["clipping_range_m"][0] >= stereo["clipping_range_m"][1]:
            raise ValueError("Invalid stereo clipping range")
        for key in ("backscatter_value", "atten_coeff", "backscatter_coeff"):
            vector(c["underwater"][key], f"underwater.{key}")
            if min(c["underwater"][key]) < 0:
                raise ValueError(f"underwater.{key} cannot be negative")
        number(c["underwater"]["max_range_m"], "underwater.max_range_m")
        number(c["underwater"]["depth_noise_sigma"], "underwater.depth_noise_sigma", strict=False)
        number(c["simulation"]["fps"], "simulation.fps")
        for key in ("warmup_frames", "rt_subframes", "readiness_attempts", "headless_frames"):
            integer(c["simulation"][key], f"simulation.{key}")
        integer(c["simulation"]["seed"], "simulation.seed", 0)
        number(water["wave"]["amplitude_m"], "water.wave.amplitude_m", strict=False)
        number(water["wave"]["initial_time_s"], "water.wave.initial_time_s", strict=False)
        number(water["wave"]["wind_speed_m_s"], "water.wave.wind_speed_m_s", strict=False)
        number(water["wave"]["scale"], "water.wave.scale")
        for key, maximum in (("photon_count_multiplier", 5000), ("photon_max_bounces", 20), ("filter_steps", 10)):
            integer(c["rtx"][key], f"rtx.{key}", 0 if key == "filter_steps" else 1)
            if c["rtx"][key] > maximum:
                raise ValueError(f"rtx.{key} exceeds OceanSim's supported range")
        if c["rtx"]["caustics"] and c["runtime"]["renderer"] != "RaytracedLighting":
            raise ValueError("Photon caustics require the configured legacy RaytracedLighting renderer")
        if c["runtime"]["backend"] not in ("d3d12", "vulkan"):
            raise ValueError("runtime.backend must be d3d12 or vulkan")
        for key in ("before_position_m", "displacement_m"):
            vector(c["changes"][key], f"changes.{key}")
        for position in (c["changes"]["before_position_m"], [a + b for a, b in zip(c["changes"]["before_position_m"], c["changes"]["displacement_m"])]):
            # Original movable crate has a 0.62 x 0.46 x 0.60 m body.
            if abs(position[0]) + 0.32 >= (w - tank["wall_thickness_m"]) / 2 or abs(position[1]) + 0.24 >= (l - tank["wall_thickness_m"]) / 2 or position[2] < 0.3:
                raise ValueError("Changed crate must stay inside tank walls and above the floor in both passes")
        lighting = c["lighting"]
        vector(lighting["size_m"], "lighting.size_m", 2, True)
        vector(lighting["colour"], "lighting.colour")
        number(lighting["intensity"], "lighting.intensity")
        number(lighting["height_above_tank_m"], "lighting.height_above_tank_m")
        if not lighting["positions_xy_m"]:
            raise ValueError("Configure at least one overhead light")
        for position in lighting["positions_xy_m"]:
            vector(position, "lighting.positions_xy_m", 2)
        integer(c["experiment"]["frames_per_pass"], "experiment.frames_per_pass")
        points = c["experiment"]["trajectory"]
        if not points or points[0]["frame"] != 0:
            raise ValueError("Trajectory must start at frame 0")
        previous = -1
        for point in points:
            integer(point["frame"], "trajectory.frame", 0)
            if point["frame"] <= previous:
                raise ValueError("Trajectory frames must be strictly increasing")
            previous = point["frame"]
            vector(point["position_m"], "trajectory.position_m")
            vector(point["rotation_xyz_deg"], "trajectory.rotation_xyz_deg")
        resolve_path(c["output"]["directory"])
    except (KeyError, TypeError) as error:
        raise ValueError(f"Incomplete or malformed configuration: {error}") from error


def find_oceansim_extension(cfg, override=None):
    value = override or os.environ.get("OCEANSIM_EXT_PATH") or cfg["runtime"]["oceansim_extension"]
    if value:
        candidates = [resolve_path(value)]
    else:
        install = os.environ.get("ISAAC_PATH") or os.environ.get("ISAAC_SIM_PATH")
        candidates = []
        if install:
            base = resolve_path(install)
            candidates = [base / "extsUser/OceanSim", base / "_build/windows-x86_64/release/extsUser/OceanSim"]
    for candidate in candidates:
        if (candidate / "config/extension.toml").is_file():
            return candidate
    raise FileNotFoundError("OceanSim extension not found. Set OCEANSIM_EXT_PATH or use --oceansim-ext (directory containing config/extension.toml).")
