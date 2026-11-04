"""Two deterministic passes through one stage, differing only in crate position."""
from __future__ import annotations


def object_position(cfg, pass_name):
    before = cfg["changes"]["before_position_m"]
    delta = cfg["changes"]["displacement_m"]
    if pass_name not in ("before", "after"):
        raise ValueError(f"Unknown inspection pass: {pass_name}")
    return [p + (d if pass_name == "after" else 0) for p, d in zip(before, delta)]


def trajectory_pose(points, frame):
    """Linear translation and shortest per-axis Euler interpolation; then hold."""
    if frame <= points[0]["frame"]:
        return points[0]["position_m"], points[0]["rotation_xyz_deg"]
    for start, end in zip(points, points[1:]):
        if frame <= end["frame"]:
            alpha = (frame - start["frame"]) / (end["frame"] - start["frame"])
            position = [a + alpha * (b - a) for a, b in zip(start["position_m"], end["position_m"])]
            angles = [a + alpha * ((b - a + 180) % 360 - 180)
                      for a, b in zip(start["rotation_xyz_deg"], end["rotation_xyz_deg"])]
            return position, angles
    return points[-1]["position_m"], points[-1]["rotation_xyz_deg"]


def prepare_pass(stage, cfg, pass_name):
    from scenes.equipment import move_changed_object
    from robots.bluerov import set_pose

    move_changed_object(stage, object_position(cfg, pass_name))
    set_pose(stage, *trajectory_pose(cfg["experiment"]["trajectory"], 0))
