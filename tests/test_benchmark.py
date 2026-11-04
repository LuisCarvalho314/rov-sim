"""CPU-only benchmark accounting and command-line tests."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark import Benchmark, percentile
from config import load_config
from run import main, parse_args


class BenchmarkTests(unittest.TestCase):
    def test_statistics_throughput_retries_and_reports(self):
        cfg = load_config()
        benchmark = Benchmark(cfg, recording=False, warmup=8)
        for index, (start, elapsed, retries) in enumerate(((100, 40, 0), (150, 60, 2), (220, 50, 1))):
            row = {"frame": index, "pass": "before", "simulation_time_s": index / 30,
                   "scene_update_ms": 2, "render_ms": elapsed - 20,
                   "annotator_acquisition_ms": 1, "underwater_processing_ms": None,
                   "gpu_readback_ms": None, "processing_readback_combined_ms": 19,
                   "recording_ms": 0, "acquisition_total_ms": elapsed,
                   "iteration_total_ms": elapsed, "readiness_retries": retries}
            benchmark.add(row, start_ns=start * 1_000_000,
                          acquisition_end_ns=(start + elapsed) * 1_000_000,
                          iteration_end_ns=(start + elapsed) * 1_000_000)
        result = benchmark.summary()
        self.assertEqual(result["stereo_pairs"], 3)
        self.assertAlmostEqual(result["effective_pairs_per_s"], 3 / .17)
        self.assertEqual(result["median_interval_fps"], 1000 / 60)
        self.assertEqual(result["frame_time"]["mean_ms"], 50)
        self.assertEqual(result["frame_time"]["median_ms"], 50)
        self.assertEqual(result["frame_time"]["p95_ms"], 59)
        self.assertEqual(result["missed_deadlines"], 1)
        self.assertEqual(result["readiness_retries"], 3)
        self.assertEqual(result["stage_statistics"]["render_ms"]["cumulative_ms"], 90)
        self.assertIsNone(result["stage_statistics"]["gpu_readback_ms"])
        with tempfile.TemporaryDirectory() as folder:
            report = benchmark.write(folder, calibration={"resolution_wh": [752, 480], "baseline_m": .38}, render_validation={})
            self.assertFalse(report["recording_enabled"])
            self.assertEqual(report["warmup_frames_per_pass"], 8)
            with (Path(folder) / "benchmark_frames.csv").open(encoding="utf-8") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 3)
            self.assertEqual(json.loads((Path(folder) / "benchmark.json").read_text())["summary"]["stereo_pairs"], 3)
            self.assertFalse(list(Path(folder).rglob("*.png")))

    def test_percentiles(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 90), 4.6)
        self.assertIsNone(percentile([], 95))

    def test_pass_warmup_gap_excluded(self):
        bench = Benchmark(load_config(), recording=False, warmup=8)
        for name, start in (("before", 100), ("after", 10_000)):
            bench.add({"pass": name, "acquisition_total_ms": 40, "iteration_total_ms": 40,
                       "readiness_retries": 0}, start_ns=start * 1_000_000,
                      acquisition_end_ns=(start + 40) * 1_000_000,
                      iteration_end_ns=(start + 40) * 1_000_000)
        self.assertAlmostEqual(bench.summary()["acquisition_wall_clock_s"], .08)

    def test_cli_modes(self):
        self.assertFalse(parse_args([]).benchmark)
        self.assertFalse(parse_args(["--record"]).benchmark)
        self.assertTrue(parse_args(["--benchmark", "--headless", "--frames", "300"]).benchmark)
        with self.assertRaises(SystemExit):
            parse_args(["--benchmark", "--frames", "0"])
        self.assertEqual(main(["--validate-only", "--benchmark"]), 0)
        self.assertEqual(main(["--validate-only", "--benchmark", "--record", "--preview-mp4"]), 0)


if __name__ == "__main__":
    unittest.main()
