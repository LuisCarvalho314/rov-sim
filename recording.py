"""Paired PNG capture plus separate pose ground truth; no extra dependencies."""
from __future__ import annotations

import json
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def create_run_directory(root):
    directory = Path(root) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


def write_png(path, frame):
    """Write OceanSim's uint8 RGB(A) buffer using the standard library."""
    if str(frame.dtype) != "uint8" or frame.ndim != 3 or frame.shape[2] not in (3, 4):
        raise ValueError(f"Expected uint8 RGB(A), got {frame.dtype} {frame.shape}")
    height, width, channels = frame.shape

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    data = b"".join(b"\x00" + row.tobytes() for row in frame)
    content = b"\x89PNG\r\n\x1a\n"
    content += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6 if channels == 4 else 2, 0, 0, 0))
    content += chunk(b"IDAT", zlib.compress(data))
    content += chunk(b"IEND", b"")
    Path(path).write_bytes(content)


class PoseRecorder:
    def __init__(self, directory, *, images):
        self.directory, self.images = Path(directory), images
        self.directory.mkdir(parents=True, exist_ok=False)
        self.file = (self.directory / "poses.jsonl").open("w", encoding="utf-8")
        if images:
            for side in ("left", "right"):
                (self.directory / side).mkdir()

    def record(self, frame_index, time_s, frames, poses):
        files = {}
        if self.images:
            for side, frame in frames.items():
                relative = f"{side}/{frame_index:06d}.png"
                write_png(self.directory / relative, frame)
                files[side] = relative
        payload = {"frame": frame_index, "time_s": time_s, "images": files, **poses}
        self.file.write(json.dumps(payload, allow_nan=False) + "\n")
        self.file.flush()

    def close(self):
        self.file.close()
