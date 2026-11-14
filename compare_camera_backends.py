"""Validate and summarize camera_backend_suite evidence using ordinary Python."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import statistics

import numpy as np

from camera_backend_suite import BACKENDS


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def matched_configuration(cfg):
    result = copy.deepcopy(cfg)
    result["stereo"].pop("backend", None)
    result["stereo"].pop("readback_degraded_depth", None)
    result["output"].pop("directory", None)
    return result


def completed_run(case):
    runs = list(Path(case).glob("*/status.json"))
    if len(runs) != 1 or read(runs[0])["state"] != "complete":
        raise ValueError(f"Expected one complete run in {case}")
    manifest = read(Path(case) / "case.json")
    if manifest["exit_code"] != 0:
        raise ValueError(f"Failed process in {case}")
    return runs[0].parent


def summarize_reports(reports):
    if not reports:
        raise ValueError("No reports")
    expected = matched_configuration(reports[0]["configuration"])
    mode = reports[0]["measurement_mode"]
    for report in reports:
        if matched_configuration(report["configuration"]) != expected or report["measurement_mode"] != mode:
            raise ValueError("Unmatched configuration or measurement mode")
        if report.get("tracy_enabled") or report.get("warp_gpu_timing"):
            raise ValueError("Instrumented reports cannot enter ordinary throughput comparison")
    count = sum(r["summary"]["stereo_pairs"] for r in reports)
    elapsed = sum(r["summary"]["acquisition_wall_clock_s"] for r in reports)
    drain = sum(r["summary"].get("gpu_drain_ms") or 0 for r in reports) / 1000
    rates = [r["summary"]["stereo_pairs"] / (r["summary"]["acquisition_wall_clock_s"] +
              (r["summary"].get("gpu_drain_ms") or 0) / 1000) for r in reports]
    stages = {}
    for name in reports[0]["summary"]["stage_statistics"]:
        values = [r["summary"]["stage_statistics"][name] for r in reports]
        stages[name] = (sum(v["cumulative_ms"] for v in values) / count if all(v is not None for v in values) else None)
    return {"runs": len(reports), "completed_pairs_steps_or_jobs": count,
            "pooled_per_s": count / (elapsed + drain), "individual_per_s": rates,
            "stdev_per_s": statistics.stdev(rates) if len(rates) > 1 else None,
            "mean_stage_ms": stages, "total_readiness_retries": sum(r["summary"]["readiness_retries"] for r in reports),
            "memory_samples": [r.get("memory_samples") for r in reports],
            "unit": reports[0]["summary"]["throughput_unit"],
            "scope": "render + acquisition + OceanSim GPU work; no-readback includes final GPU drain"}


def wall_range_check(arrays, pose, calibration, side):
    """Original bare east wall, independent of measured depth. Uses pixel centres."""
    transform = np.array(pose["T_world_optical"][side])
    k = np.array(calibration["K"][side])
    world = np.array([3.9, -1.1, 1.9])
    optical = transform[:3, :3].T @ (world - transform[:3, 3])
    uvw = k @ optical
    u, v = np.floor(uvw[:2] / uvw[2]).astype(int)
    depth = arrays[f"{side}_clean_range_m"]
    if not (0 <= v < depth.shape[0] and 0 <= u < depth.shape[1]):
        raise ValueError("Bare wall reference is outside the original camera view")
    ray = np.array([(u + .5 - k[0, 2]) / k[0, 0], (v + .5 - k[1, 2]) / k[1, 1], 1.])
    direction = transform[:3, :3] @ ray
    expected = (3.9 - transform[0, 3]) / direction[0] * np.linalg.norm(ray)
    error = abs(float(depth[v, u]) - expected)
    # A loose geometry tolerance can accept a whole stale trajectory frame.
    # This bare plane is analytically known, so require millimetre agreement.
    if error > .001:
        raise ValueError(f"{side} bare wall radial range/orientation error: {error:.5f} m")
    return error


def validate_captures(root, tiled_root=None):
    from validate_photometry import verify_saved
    from validate_recording import read_png
    from evaluate_photometry import poses, luminance
    runs = {b: completed_run((tiled_root if b == "tiled" and tiled_root else root) / "validation" / b) for b in BACKENDS}
    baseline_cfg = matched_configuration(read(runs["legacy"] / "config.json"))
    baseline_cal = read(runs["legacy"] / "stereo_calibration.json")
    baseline_poses = {p: poses(runs["legacy"], p) for p in ("before", "after")}
    result = {}
    for backend, run in runs.items():
        cfg, cal = read(run / "config.json"), read(run / "stereo_calibration.json")
        if matched_configuration(cfg) != baseline_cfg:
            raise ValueError(f"Unmatched capture configuration: {backend}")
        for key in ("K", "T_body_optical"):
            for side in ("left", "right"):
                # Legacy exports K as float32, while USD-derived K is float64.
                # Existing initialization uses the same 1e-4-pixel tolerance.
                tolerance = 1e-4 if key == "K" else 1e-6
                if not np.allclose(cal[key][side], baseline_cal[key][side], atol=tolerance, rtol=0):
                    raise ValueError(f"Calibration changed: {backend}/{key}/{side}")
        check = verify_saved(run)
        counts, wall_errors, cross = 0, [], []
        for session in ("before", "after"):
            records = poses(run, session)
            original_records = baseline_poses[session]
            if records.keys() != original_records.keys():
                raise ValueError(f"Recorded frame indices differ: {backend}/{session}")
            for frame, record in records.items():
                expected = original_records[frame]
                for key in record:
                    if key == "T_world_optical":
                        same = all(np.allclose(record[key][s], expected[key][s], atol=1e-6, rtol=0) for s in ("left", "right"))
                    elif key.startswith("T_"):
                        same = np.allclose(record[key], expected[key], atol=1e-6, rtol=0)
                    else:
                        same = record[key] == expected[key]
                    if not same:
                        raise ValueError(f"Recorded {key} differs: {backend}/{session}/{frame}")
            for frame in records:
                for side in ("left", "right"):
                    image = read_png(run / session / side / f"{frame:06d}.png")
                    if image.shape != (480, 752, 4) or image[..., :3].std() <= 1:
                        raise ValueError("Invalid or uninformative PNG")
                    counts += 1
            for path in sorted((run / "photometry").glob(f"{session}_*.npz")):
                frame = int(path.stem.split("_")[1])
                meta = read(path.with_name(path.stem + "_metadata.json"))
                if backend != "legacy":
                    equivalence = meta["equivalent_input_processing"]
                    if not all(all(v.values()) for v in equivalence.values()):
                        raise ValueError("Production OceanSim equivalence failed")
                with np.load(path) as arrays, np.load(runs["legacy"] / "photometry" / path.name) as legacy:
                    for side in ("left", "right"):
                        wall_errors.append(wall_range_check(arrays, records[frame], cal, side))
                        a, b = (x[f"{side}_clean_range_m"] for x in (arrays, legacy))
                        valid = np.isfinite(a) & np.isfinite(b)
                        depth_error = np.abs(a[valid] - b[valid])
                        raw = np.abs(arrays[f"{side}_raw_rgba"].astype(float) - legacy[f"{side}_raw_rgba"])
                        cross.append({"pass": session, "frame": frame, "side": side,
                                      "range_mae_m": float(depth_error.mean()),
                                      "range_p99_m": float(np.percentile(depth_error, 99)),
                                      "range_fraction_gt1mm": float((depth_error > .001).mean()),
                                      "raw_rgb_mae_levels": float(raw[..., :3].mean()),
                                      "raw_rgb_p95_levels": float(np.percentile(raw[..., :3], 95))})
        result[backend] = {**check, "recorded_pngs_crc_checked": counts,
                           "calibration_and_all_poses_match_legacy": True,
                           "K_max_abs_difference_px": float(max(np.max(np.abs(np.array(cal['K'][s]) - baseline_cal['K'][s])) for s in ('left', 'right'))),
                           "wall_radial_range_max_error_m": max(wall_errors),
                           "cross_backend_same_pose": cross}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--captures-only", action="store_true")
    parser.add_argument("--benchmarks-only", action="store_true")
    parser.add_argument("--tiled-root", type=Path, help="Use corrected tiled cases from this evidence root")
    args = parser.parse_args()
    report = {}
    if not args.benchmarks_only:
        report["validation"] = validate_captures(args.root, args.tiled_root)
    if not args.captures_only:
        report["benchmarks"] = {}
        exclusions_path = args.root / "excluded_cases.json"
        exclusions = read(exclusions_path) if exclusions_path.exists() else {}
        report["excluded_cases"] = exclusions
        for mode in ("full", "render-only", "no-readback", "depth-readback"):
            report["benchmarks"][mode] = {}
            expected_config = None
            for backend in BACKENDS:
                source_root = args.tiled_root if backend == "tiled" and args.tiled_root else args.root
                cases = sorted((source_root / mode).glob(f"{backend}_*"))
                cases = [case for case in cases if f"{mode}/{case.name}" not in exclusions]
                if not cases:
                    continue
                reports = [read(completed_run(case) / "benchmark.json") for case in cases]
                for item in reports:
                    config = matched_configuration(item["configuration"])
                    if expected_config is not None and config != expected_config:
                        raise ValueError(f"Unmatched backend configurations in {mode}")
                    expected_config = config
                summary = summarize_reports(reports)
                report["benchmarks"][mode][backend] = summary
                print(f"{mode:16s} {backend:14s} {summary['pooled_per_s']:.3f}/s {summary['individual_per_s']}")
    report["evidence_roots"] = {"legacy_and_individual": str(args.root), "tiled": str(args.tiled_root or args.root)}
    filename = "camera_comparison_validated.json" if args.tiled_root else "camera_comparison.json"
    path = args.root / ("capture_validation.json" if args.captures_only else filename)
    path.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(f"WROTE {path}")


if __name__ == "__main__":
    main()
