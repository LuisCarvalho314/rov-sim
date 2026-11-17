"""CPU-only wall-clock accounting for complete processed stereo pairs."""
from __future__ import annotations

import csv
import platform
import statistics
from pathlib import Path

from rov_sim.recording import write_json

TARGET_FPS = 20.0
BUDGET_MS = 1000.0 / TARGET_FPS
STAGES = ("scene_update_ms", "render_ms", "annotator_acquisition_ms",
          "underwater_processing_ms", "gpu_readback_ms", "gpu_synchronization_ms",
          "processing_readback_combined_ms", "recording_ms")
COLUMNS = ("frame", "pass", "simulation_time_s", *STAGES,
           "acquisition_total_ms", "iteration_total_ms", "readiness_retries")


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    fraction = position - lower
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * fraction


def distribution(values):
    return {"mean_ms": statistics.mean(values), "median_ms": percentile(values, 50),
            "p90_ms": percentile(values, 90), "p95_ms": percentile(values, 95),
            "p99_ms": percentile(values, 99), "min_ms": min(values), "max_ms": max(values)} if values else None


class Benchmark:
    def __init__(self, cfg, *, recording, warmup, gpu=None, versions=None, mode="full", tracy=False, mcap=None):
        self.cfg = cfg
        self.recording = recording
        self.warmup = warmup
        self.gpu = gpu
        self.versions = versions or {}
        self.mode = mode
        self.tracy = tracy
        self.mcap = mcap
        self.rows = []
        self.first_start_ns = None
        self.last_acquisition_end_ns = None
        self.last_iteration_end_ns = None
        self.starts_ns = []
        self.acquisition_ns = 0
        self.iteration_ns = 0
        self.pass_start_ns = None
        self.current_pass = None

    def add(self, row, *, start_ns, acquisition_end_ns, iteration_end_ns):
        if self.first_start_ns is None:
            self.first_start_ns = start_ns
        if row["pass"] != self.current_pass:
            if self.current_pass is not None:
                self.acquisition_ns += self.last_acquisition_end_ns - self.pass_start_ns
                self.iteration_ns += self.last_iteration_end_ns - self.pass_start_ns
            self.current_pass = row["pass"]
            self.pass_start_ns = start_ns
        self.last_acquisition_end_ns = acquisition_end_ns
        self.last_iteration_end_ns = iteration_end_ns
        self.starts_ns.append(start_ns)
        self.rows.append({key: row.get(key) for key in COLUMNS})

    def summary(self):
        rows = self.rows
        count = len(rows)
        acquisition_s = (self.acquisition_ns + self.last_acquisition_end_ns - self.pass_start_ns) / 1e9 if count else 0.0
        iteration_s = (self.iteration_ns + self.last_iteration_end_ns - self.pass_start_ns) / 1e9 if count else 0.0
        frames = [row["acquisition_total_ms"] for row in rows]
        intervals = [(b - a) / 1e6 for i, (a, b) in enumerate(zip(self.starts_ns, self.starts_ns[1:]))
                     if rows[i]["pass"] == rows[i + 1]["pass"]]
        missed = sum(value > BUDGET_MS for value in frames)
        stages = {}
        for name in STAGES:
            values = [row[name] for row in rows if row[name] is not None]
            stages[name] = ({"cumulative_ms": sum(values), "mean_ms": statistics.mean(values),
                             "p95_ms": percentile(values, 95),
                             "frame_budget_percent_mean": statistics.mean(values) / BUDGET_MS * 100}
                            if len(values) == count and count else None)
        fps = count / acquisition_s if acquisition_s else 0.0
        return {"stereo_pairs": count, "acquisition_wall_clock_s": acquisition_s,
                "iteration_wall_clock_s": iteration_s, "effective_pairs_per_s": fps,
                "iteration_pairs_per_s": count / iteration_s if iteration_s else 0.0,
                "simulation_time_fps": self.cfg["simulation"]["fps"],
                "gui_viewport_fps": None,
                "median_interval_fps": 1000 / percentile(intervals, 50) if intervals else None,
                "frame_time": distribution(frames), "stage_statistics": stages,
                "missed_deadlines": missed, "missed_deadline_percent": 100 * missed / count if count else 0,
                "readiness_retries": sum(row["readiness_retries"] for row in rows),
                "target_fps": TARGET_FPS, "frame_budget_ms": BUDGET_MS,
                "achieved_to_target_ratio": fps / TARGET_FPS}

    def progress(self, expected):
        result = self.summary()
        frame = result["frame_time"]
        unit = "pairs" if self.mode == "full" else "steps" if self.mode == "render-only" else "jobs"
        return (f"[Benchmark] {len(self.rows)}/{expected} {unit} | "
                f"{result['effective_pairs_per_s']:.1f} {unit}/s | mean {frame['mean_ms']:.1f} ms | "
                f"p95 {frame['p95_ms']:.1f} ms")

    def write(self, directory, *, calibration, render_validation, mp4_encoding_s=None, drain_ms=0.0,
              warp_gpu_timing=None):
        directory = Path(directory)
        with (directory / "benchmark_frames.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)
        summary = self.summary()
        summary["throughput_unit"] = "processed_stereo_pairs" if self.mode == "full" else "stereo_render_steps" if self.mode == "render-only" else "ocean_gpu_jobs"
        summary["gpu_drain_ms"] = drain_ms if self.mode == "no-readback" else None
        summary["drain_inclusive_jobs_per_s"] = (len(self.rows) / (summary["acquisition_wall_clock_s"] + drain_ms / 1000)
                                                   if self.mode == "no-readback" else None)
        report = {"summary": summary, "configuration": self.cfg,
                  "camera_backend": self.cfg["stereo"].get("backend", "legacy"),
                  "measurement_mode": self.mode, "tracy_enabled": self.tracy,
                  "warp_gpu_timing": warp_gpu_timing,
                  "active_renderer": render_validation.get("renderer_readback"),
                  "actual_resolution_wh": calibration["resolution_wh"],
                  "actual_baseline_m": calibration["baseline_m"],
                  "renderer": render_validation, "rt_subframes": self.cfg["simulation"]["rt_subframes"],
                  "animated_water": self.cfg["water"]["wave"], "recording_enabled": self.recording,
                  "warmup_frames_per_pass": self.warmup, "gpu": self.gpu,
                  "versions": {"python": platform.python_version(), **self.versions},
                  "mp4_encoding_s": mp4_encoding_s,
                  "measurement_notes": [
                      "camera_backend identifies acquisition. Experimental backends split acquisition, kernel submission and requested RGB readback; degraded depth readback is opt-in. Legacy normal capture retains UW_Camera.render(), including its mandatory RGB and degraded-depth readbacks.",
                      "Experimental no-readback runs fence their Warp stream before the next render can reuse borrowed annotator buffers. gpu_synchronization_ms records this wait separately from rendering; no-readback throughput also includes the final GPU drain.",
                      "Throughput uses wall-clock time from the first measured scene update to the last measured step/job/pair; startup and warmup are excluded.",
                      "Normal full capture uses OceanSim UW_Camera.render(). Diagnostic full/no-readback modes mirror OceanSim 1.0.0 kernel calls with separate CPU wall timings; underwater_processing_ms is host enqueue time, while gpu_readback_ms includes .numpy() transfer plus any GPU synchronization wait. Neither is pure GPU execution time.",
                      "Render-only and no-readback throughput counts submitted steps/jobs, not acquired CPU stereo pairs. No-readback reports a final GPU drain separately; validation images are acquired outside measured frames.",
                      "Optional Warp CUDA activity timing inserts events and a final synchronization; it adds overhead and excludes RTX/DX12 GPU work. It is never enabled in normal runs.",
                      "annotator_acquisition_ms measures the external RGB/depth readiness checks. OceanSim's internal annotator fetches are included in processing_readback_combined_ms.",
                      "render_ms measures blocking rep.orchestrator.step() wall time, including its wait_for_render behavior and retries; it is not a pure GPU kernel time.",
                      "Frame latency and end-to-end throughput differ; simulation timestamps and GUI FPS are not execution throughput.",
                  ]}
        if self.mcap is not None:
            report["mcap"] = self.mcap
        write_json(directory / "benchmark.json", report)
        return report
