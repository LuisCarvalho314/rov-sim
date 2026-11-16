"""Post-capture MP4 previews made only from the recorded PNG sequences."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _frames(directory):
    directory = Path(directory)
    files = sorted(directory.glob("*.png"))
    if not files:
        raise ValueError(f"No PNG frames in {directory}")
    indices = []
    for path in files:
        if len(path.stem) != 6 or not path.stem.isdecimal():
            raise ValueError(f"Unexpected PNG frame name: {path}")
        indices.append(int(path.stem))
    expected = list(range(len(indices)))
    if indices != expected:
        raise ValueError(f"Missing or nonconsecutive PNG frames in {directory}: expected {expected}, found {indices}")
    return indices


def _timestamps(pass_directory, indices):
    path = Path(pass_directory) / "poses.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [row["frame"] for row in records] != indices:
        raise ValueError(f"Pose frame indices do not match PNGs in {pass_directory}")
    return [row["time_s"] for row in records]


def _paired(first, second):
    left, right = _frames(first), _frames(second)
    if left != right:
        raise ValueError(f"PNG frame indices/counts differ between {first} and {second}")
    return left


def ffmpeg_command(executable, first, second, output, cfg):
    """Build one FFmpeg invocation for two numbered PNG sequences."""
    fps = str(cfg["fps"])
    return [str(executable), "-hide_banner", "-loglevel", "error", "-n",
            "-framerate", fps, "-start_number", "0", "-i", str(Path(first) / "%06d.png"),
            "-framerate", fps, "-start_number", "0", "-i", str(Path(second) / "%06d.png"),
            "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]", "-map", "[v]",
            "-c:v", cfg["codec"], "-crf", str(cfg["crf"]), "-preset", cfg["preset"],
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]


def _encode(executable, first, second, output, cfg, indices):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Preview already exists: {output}")
    command = ffmpeg_command(executable, first, second, output, cfg)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise RuntimeError(f"Could not run FFmpeg for {output}: {error}") from error
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed for {output} (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    if not output.is_file():
        raise RuntimeError(f"FFmpeg reported success but did not create {output}")
    return {"file": str(output), "frames": len(indices), "fps": cfg["fps"], "state": "complete"}


def generate_previews(run_directory, passes, cfg, *, on_result=None):
    """Validate pairings, then encode stereo passes and optional comparison."""
    directory = Path(run_directory)
    executable = cfg["ffmpeg_executable"] or shutil.which("ffmpeg")
    if not executable:
        raise FileNotFoundError("FFmpeg not found; install FFmpeg or set output.preview.ffmpeg_executable")
    indices_by_pass = {}
    for name in passes:
        pass_dir = directory / name
        indices_by_pass[name] = _paired(pass_dir / "left", pass_dir / "right")
        _timestamps(pass_dir, indices_by_pass[name])
    if len(passes) == 2:
        before, after = passes
        if indices_by_pass[before] != indices_by_pass[after]:
            raise ValueError("Before/after PNG frame indices or counts differ")
        if _timestamps(directory / before, indices_by_pass[before]) != _timestamps(directory / after, indices_by_pass[after]):
            raise ValueError("Before/after pose timestamps differ")
    results = {}
    for name in passes:
        pass_dir = directory / name
        results[f"{name}_stereo"] = _encode(executable, pass_dir / "left", pass_dir / "right",
                                             pass_dir / "stereo_preview.mp4", cfg, indices_by_pass[name])
        if on_result:
            on_result(f"{name}_stereo", results[f"{name}_stereo"])
    if len(passes) == 2:
        results["comparison"] = _encode(executable, directory / passes[0] / "left", directory / passes[1] / "left",
                                        directory / "comparison_preview.mp4", cfg, indices_by_pass[passes[0]])
        if on_result:
            on_result("comparison", results["comparison"])
    return results
