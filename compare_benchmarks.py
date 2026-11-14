"""Compare benchmark.json reports from repeated configuration runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def latest_profile_reports(root):
    """Find the newest completed 300-pair run for each renderer profile."""
    profiles = {("RealTimePathTracing", False): "A",
                ("RaytracedLighting", False): "B",
                ("RaytracedLighting", True): "C"}
    found = {}
    for path in root.glob("*/benchmark.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            cfg = report["configuration"]
            key = (report.get("active_renderer") or cfg["runtime"]["renderer"], cfg["rtx"]["caustics"])
            if (key in profiles and report.get("measurement_mode", "full") == "full"
                    and cfg["simulation"]["rt_subframes"] == 1
                    and not report["recording_enabled"] and report["summary"]["stereo_pairs"] == 300):
                name = profiles[key]
                if name not in found or path.stat().st_mtime > found[name].stat().st_mtime:
                    found[name] = path
        except (OSError, ValueError, KeyError, TypeError):
            continue
    missing = set(profiles.values()) - found.keys()
    if missing:
        raise ValueError(f"No completed 300-pair benchmark for profile(s) {', '.join(sorted(missing))} under {root}")
    return [found[name] for name in ("A", "B", "C")]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="*", type=Path, help="Run directories or benchmark.json files")
    parser.add_argument("--latest-profiles", type=Path, metavar="OUTPUTS_DIR",
                        help="Compare the newest completed A/B/C 300-pair runs under this directory")
    args = parser.parse_args(argv)
    if args.latest_profiles:
        if args.reports:
            parser.error("Use either report paths or --latest-profiles")
        try:
            args.reports = latest_profile_reports(args.latest_profiles)
        except ValueError as error:
            parser.error(str(error))
    elif not args.reports:
        parser.error("Provide report paths or --latest-profiles outputs")
    for path in args.reports:
        if "<" in str(path) or ">" in str(path):
            parser.error(f"{path} is a placeholder; pass an actual run directory or use --latest-profiles outputs")
        target = path / "benchmark.json" if path.is_dir() else path
        if not target.is_file():
            parser.error(f"Benchmark report not found: {target}")
    print("profile\trenderer\tcaustics\tsubframes\trecord\tpairs/s\tp95 ms\tmissed %\trender mean ms\tprocess+readback mean ms\trecord mean ms")
    for path in args.reports:
        report = json.loads((path / "benchmark.json" if path.is_dir() else path).read_text(encoding="utf-8"))
        cfg, summary = report["configuration"], report["summary"]
        stages = summary["stage_statistics"]
        def mean(name):
            stage = stages[name]
            return f"{stage['mean_ms']:.2f}" if stage else "NA"
        print(f"{path.parent.name if path.is_file() else path.name}\t{report.get('active_renderer') or cfg['runtime']['renderer']}\t{cfg['rtx']['caustics']}\t"
              f"{cfg['simulation']['rt_subframes']}\t{report['recording_enabled']}\t"
              f"{summary['effective_pairs_per_s']:.2f}\t{summary['frame_time']['p95_ms']:.2f}\t"
              f"{summary['missed_deadline_percent']:.1f}\t{mean('render_ms')}\t"
              f"{mean('processing_readback_combined_ms')}\t{mean('recording_ms')}")


if __name__ == "__main__":
    main()
