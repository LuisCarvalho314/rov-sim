"""Verify saved stereo PNGs, calibration and poses without launching Kit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import zlib

import numpy as np

from experiments.change_detection import trajectory_pose
from recording import write_json


def read_png(path):
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG: {path}")
    offset, payload = 8, bytearray()
    while offset < len(data):
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        tag, chunk = data[offset + 4:offset + 8], data[offset + 8:offset + 8 + size]
        crc = struct.unpack(">I", data[offset + 8 + size:offset + 12 + size])[0]
        assert zlib.crc32(tag + chunk) & 0xFFFFFFFF == crc, f"PNG CRC: {path}"
        if tag == b"IHDR":
            width, height, bits, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk)
            assert bits == 8 and color in (2, 6) and not any((compression, filtering, interlace))
            channels = 4 if color == 6 else 3
        if tag == b"IDAT":
            payload.extend(chunk)
        offset += size + 12
    scanlines = np.frombuffer(zlib.decompress(payload), dtype=np.uint8).reshape(height, 1 + width * channels)
    assert np.all(scanlines[:, 0] == 0), "Expected the existing recorder's PNG filter=0"
    return scanlines[:, 1:].reshape(height, width, channels)


def validate(directory):
    directory = Path(directory)
    status = json.loads((directory / "status.json").read_text())
    assert status["state"] == "complete", status
    cfg = json.loads((directory / "config.json").read_text())
    calibration = json.loads((directory / "stereo_calibration.json").read_text())
    diagnostics = json.loads((directory / "diagnostics/summary.json").read_text())
    assert diagnostics["status"] == "PASS"
    all_poses, count = {}, 0
    for pass_name, expected_count in status["completed_frames"].items():
        folder = directory / pass_name
        poses = [json.loads(line) for line in (folder / "poses.jsonl").read_text().splitlines()]
        assert len(poses) == expected_count
        expected_names = {f"{i:06d}.png" for i in range(expected_count)}
        for side in ("left", "right"):
            assert {p.name for p in (folder / side).glob("*.png")} == expected_names
        for index, pose in enumerate(poses):
            assert pose["frame"] == index and abs(pose["time_s"] - index / cfg["simulation"]["fps"]) < 1e-9
            frames = {s: read_png(folder / pose["images"][s]) for s in ("left", "right")}
            assert all(f.shape == (480, 752, 4) for f in frames.values())
            assert all(f[..., :3].std() > 1 for f in frames.values()), "Uninformative images"
            assert not np.array_equal(frames["left"], frames["right"]), "Duplicated stereo views"
            body = np.array(pose["T_world_body"])
            for side in frames:
                optical = np.array(pose["T_world_optical"][side])
                assert np.allclose(np.linalg.inv(body) @ optical, calibration["T_body_optical"][side], atol=1e-6)
            relative = np.linalg.inv(pose["T_world_optical"]["left"]) @ pose["T_world_optical"]["right"]
            assert np.allclose(relative, calibration["T_leftOptical_rightOptical"], atol=1e-6)
            if "after" in status["completed_frames"]:
                position, _ = trajectory_pose(cfg["experiment"]["trajectory"], index)
                assert np.allclose(body[:3, 3], position, atol=1e-6), "Recorded trajectory differs"
            snapshot = directory / "diagnostics" / f"{pass_name}_{index:06d}_frames.npz"
            if snapshot.exists():
                with np.load(snapshot) as arrays:
                    for side in frames:
                        assert np.array_equal(frames[side], arrays[f"{side}_underwater_rgba"])
                        raw = read_png(directory / "diagnostics" / f"{pass_name}_{index:06d}_{side}_raw.png")
                        assert np.array_equal(raw, arrays[f"{side}_raw_rgba"])
            count += 1
        all_poses[pass_name] = poses
    if "after" in all_poses:
        before, after = all_poses["before"], all_poses["after"]
        assert len(before) == len(after)
        for first, second in zip(before, after):
            for key in ("T_world_body", "T_world_optical"):
                assert first[key] == second[key], "Ground-truth path changed between passes"
            delta = np.array(second["T_world_changed_object"])[:3, 3] - np.array(first["T_world_changed_object"])[:3, 3]
            assert np.allclose(delta, cfg["changes"]["displacement_m"], atol=1e-6)
        assert not np.allclose(before[0]["T_world_body"], before[-1]["T_world_body"]), "Vehicle did not move"
    assert len(diagnostics["frames"]) == count
    result = {"status": "PASS", "verified_pairs": count, "passes": status["completed_frames"],
              "checks": "PNG CRC/pixels, paired indices, timestamps, trajectory, fixed calibration, before/after poses and crate displacement, NPZ versus recorder bytes"}
    write_json(directory / "recording_verification.json", result)
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    validate(parser.parse_args().directory)
