"""Compare benchmark.json reports from repeated configuration runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="Run directories or benchmark.json files")
    args = parser.parse_args(argv)
    print("profile\tcaustics\tsubframes\trecord\tpairs/s\tp95 ms\tmissed %\trender mean ms\tprocess+readback mean ms\trecord mean ms")
    for path in args.reports:
        report = json.loads((path / "benchmark.json" if path.is_dir() else path).read_text(encoding="utf-8"))
        cfg, summary = report["configuration"], report["summary"]
        stages = summary["stage_statistics"]
        def mean(name):
            stage = stages[name]
            return f"{stage['mean_ms']:.2f}" if stage else "NA"
        print(f"{path.parent.name if path.is_file() else path.name}\t{cfg['rtx']['caustics']}\t"
              f"{cfg['simulation']['rt_subframes']}\t{report['recording_enabled']}\t"
              f"{summary['effective_pairs_per_s']:.2f}\t{summary['frame_time']['p95_ms']:.2f}\t"
              f"{summary['missed_deadline_percent']:.1f}\t{mean('render_ms')}\t"
              f"{mean('processing_readback_combined_ms')}\t{mean('recording_ms')}")


if __name__ == "__main__":
    main()
