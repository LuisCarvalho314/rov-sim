"""Deterministic, camera-inward elliptical orbit for single-pass datasets."""
from __future__ import annotations

import math


def orbit_pose(spec, frame):
    """Return body position and XYZ angles in metres/degrees for capture frame.

    frames_per_revolution controls speed independently of capture length, so a
    short --frames smoke test follows the same first segment as the full run.
    The optional slow vertical oscillation covers different elevations across
    successive laps without introducing a pose discontinuity.
    """
    if frame < 0:
        raise ValueError("Orbit frame must be nonnegative")
    phase = 2.0 * math.pi * frame / spec["frames_per_revolution"]
    theta = math.radians(spec["start_angle_deg"]) + phase
    cx, cy = spec["centre_xy_m"]
    rx, ry = spec["radii_xy_m"]
    x = cx + rx * math.cos(theta)
    y = cy + ry * math.sin(theta)
    z = spec["height_m"] + spec["vertical_amplitude_m"] * math.sin(phase / 2.0)
    yaw = math.degrees(math.atan2(cy - y, cx - x))
    return [x, y, z], [0.0, 0.0, yaw]
